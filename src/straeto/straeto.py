"""

    straeto.py: A package encapsulating information about Icelandic buses and bus routes

    Copyright (c) 2020 Miðeind ehf.
    Original author: Vilhjálmur Þorsteinsson

       This program is free software: you can redistribute it and/or modify
       it under the terms of the GNU General Public License as published by
       the Free Software Foundation, either version 3 of the License, or
       (at your option) any later version.
       This program is distributed in the hope that it will be useful,
       but WITHOUT ANY WARRANTY; without even the implied warranty of
       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
       GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see http://www.gnu.org/licenses/.


    This module implements several classes that represent the schedule
    of Strætó bs., an Icelandic municipal bus company.

    They include:

        Bus         : A Bus, located somewhere on a particular route
        BusStop     : A location where one or more Buses stop
        BusTrip     : A particular Trip, undertaken during a day by a Bus on a Route
        BusRoute    : A Route that is driven periodically by Buses, involving Stops
        BusHalt     : A visit at at Stop by a Bus on a Trip, at a scheduled time
        BusService  : A set of Trips that are driven as a part of a Route
                      on particular dates
        BusCalendar : A mapping of dates to the Services that are active on each date
        BusSchedule : A wrapper object that can be queried about Bus arrivals at
                      particular Stops on given Routes

    The data are initialized from text files stored in the src/bus/resources directory.
    They are in turn fetched from Strætó's website.

"""

import os
import re
import math
from datetime import date, time, datetime, timedelta
import threading
import functools
from collections import defaultdict
import xml.etree.ElementTree as ET
import logging

import requests
import shutil
import zipfile


# Set _DEBUG to True to emit diagnostic messages
_DEBUG = False

_THIS_PATH = os.path.dirname(__file__) or "."

_RESOURCES_PATH = functools.partial(os.path.join, _THIS_PATH, "resources")
_CONFIG_PATH = functools.partial(os.path.join, _THIS_PATH, "config")

# The URL of the ZIPped schedule file
_SCHEDULE_URL = "http://opendata.straeto.is/data/gtfs/gtfs.zip"

# The local copy of the ZIPped schedule file
_GTFS_PATH = _RESOURCES_PATH("gtfs.zip")

# Where the URL to fetch bus status data is stored (this is not public information;
# you must apply to Straeto bs to obtain permission and get your own URL)
_STATUS_URL_FILE = _CONFIG_PATH("status_url.txt")

try:
    _STATUS_URL = open(_STATUS_URL_FILE, "r", encoding="utf-8").read().strip()
except FileNotFoundError:
    logging.warning("Unable to read '{0}'".format(_STATUS_URL_FILE))
    _STATUS_URL = None

# Real-time status refresh interval
_REFRESH_INTERVAL = 60

# Fallback location to fetch status info from, if not available via HTTP
_STATUS_FILE = _RESOURCES_PATH("status.xml")

_EARTH_RADIUS = 6371.0088  # Earth's radius in km
_MIDEIND_LOCATION = (64.156896, -21.951200)  # Fiskislóð 31, 101 Reykjavík

_VOICE_NAMES = {
    "Umferðarmiðstöðin (BSÍ)": "Umferðarmiðstöðin",
    "BSÍ": "Umferðarmiðstöðin",
    "BSÍ / Landspítalinn": "Umferðarmiðstöðin / Landspítalinn",
    "KEF - Airport": "Keflavíkurflugvöllur",
    "10-11": "Tíu ellefu",
    "Fjölbrautaskóli Suðurnesja / FS": "Fjölbrautaskóli Suðurnesja",
    "Sauðárkrókur - N1": "Sauðárkrókur - Enn einn",
    "Þórunnarstræti / MA": "Þórunnarstræti / Menntaskólinn á Akureyri",
    "Fáskrúðsfjörður / Hafnargata v. Franska sp.": "Fáskrúðsfjörður / Hafnargata við franska spítalann",
    "Stöðvarfjörður / Brekkan - uppl. miðstöð": "Stöðvarfjörður / Brekkan upplýsingamiðstöð",
    "Selfoss - N1": "Selfoss - Enn einn",
    "Selfoss - FSU": "Selfoss - Fjölbrautaskóli Suðurlands",
    "FSU": "Fjölbrautaskóli Suðurlands",
    "RÚV": "Útvarpshúsið",
    "TBR": "Tennis og badmintonfélag Reykjavíkur",
    "KR": "Knattspyrnufélag Reykjavíkur",
    "JL húsið": "JL-húsið",
    "Esjurætur - Hiking Center": "Esjurætur",
    "LSH / Hringbraut": "Landspítalinn / Hringbraut",
    "Menntaskólinn í Reykjavík / MR": "MR",
    "Menntaskólinn við Hamrahlíð / MH": "MH",
    "Menntaskólinn við Sund / MS": "MS",
    "Íþróttamiðstöð ÍR": "Íþróttamiðstöð Í R",
}

# In case of conflict between route numbers, resolve the conflict by
# looking up areas in the following order (which in practice means that '1'
# resolves to bus route number 1 in the capital area, not in the east fjords)
_DEFAULT_AREA_PRIORITY = ("ST", "SU", "VL", "SN", "NO", "RY", "AF")


def distance(loc1, loc2):
    """
    Calculate the Haversine distance.

    Parameters
    ----------
    origin : tuple of float
        (lat, long)
    destination : tuple of float
        (lat, long)

    Returns
    -------
    distance_in_km : float

    Examples
    --------
    >>> origin = (48.1372, 11.5756)  # Munich
    >>> destination = (52.5186, 13.4083)  # Berlin
    >>> round(distance(origin, destination), 1)
    504.2

    Source:
    https://stackoverflow.com/questions/19412462
        /getting-distance-between-two-points-based-on-latitude-longitude

    """
    lat1, lon1 = loc1
    lat2, lon2 = loc2

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    slat = math.sin(dlat / 2)
    slon = math.sin(dlon / 2)
    a = (
        slat * slat
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * slon * slon
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS * c


# Entfernung - used for test purposes
entf = functools.partial(distance, _MIDEIND_LOCATION)


def locfmt(loc):
    """ Return a (lat, lon) location tuple in a standard string format """
    return "({0:.6f},{1:.6f})".format(loc[0], loc[1])


def round_to_hh_mm(ts, round_down=False):
    """ Round a timestamp to a (h, m, s) tuple of the form hh:mm:00 """
    h, m, s = ts.hour, ts.minute, ts.second
    if round_down:
        # Always round down
        s = 0
    elif s > 30 or (s == 30 and (m % 2)):
        # Round up, or to an even number of minutes if seconds == 30
        s = 0
        m += 1
        if m >= 60:
            m -= 60
            h += 1
            if h >= 24:
                h -= 24
    return h, m, s


class BusCalendar:

    """ This class contains a mapping from dates to the BusServices that
        are active on each date. """

    # Call BusCalendar.initialize() to initialize the calendar
    _calendar = defaultdict(set)

    @staticmethod
    def lookup(d):
        """ Return a set of service_ids that are active on the given date """
        return BusCalendar._calendar.get(d, set())

    @staticmethod
    def today():
        """ Return a set of service_ids that are active today (UTC/Icelandic time) """
        now = datetime.utcnow()
        return BusCalendar.lookup(date(now.year, now.month, now.day))

    @staticmethod
    def initialize():
        """ Read information about the service calendar from
            the calendar_dates.txt file """
        BusCalendar._calendar = defaultdict(set)
        with open(_RESOURCES_PATH("calendar_dates.txt"), "r", encoding="utf-8",) as f:
            index = 0
            for line in f:
                index += 1
                if index == 1:
                    # Ignore first line
                    continue
                line = line.strip()
                if not line:
                    continue
                # Format is:
                # service_id,date,exception_type
                f = line.split(",")
                assert len(f) == 3
                d = f[1].strip()
                year = int(d[0:4])
                month = int(d[4:6])
                day = int(d[6:8])
                assert 2000 <= year <= 2100
                assert 1 <= month <= 12
                assert 1 <= day <= 31
                # Add this service id to the set of services that are active
                # on the indicated date
                BusCalendar._calendar[date(year, month, day)].add(f[0].strip())


class BusTrip:

    """ A BusTrip is a trip undertaken by a Bus on a particular Route,
        spanning several Stops that are visited at points in time given
        in Halts. """

    _all_trips = dict()

    def __init__(self, *, trip_id, route_id, headsign, short_name, direction, block):
        self._id = trip_id
        assert "." in route_id
        self._route_id = route_id
        self._headsign = headsign
        self._short_name = short_name
        self._direction = direction
        self._block = block
        self._halts = defaultdict(list)
        # Set of stop_ids visited on this trip
        self._stops = set()
        # Set of tuples: (stop, next_stop) for all consecutive stops on this trip
        self._consecutive_stops = set()
        # Cache a sorted list of halts and arrival times for this trip
        self._sorted_halts = None
        # Store the first and last stop ids for this trip
        self._first_stop = None
        self._last_stop_seq = 0
        self._last_stop = None
        # Store the start and end times for this trip, as (h, m, s) tuples
        self._start_time = None
        self._end_time = None
        # Accumulate a singleton database of all trips
        BusTrip._all_trips[self._id] = self

    @classmethod
    def clear(cls):
        """ Clear all trips """
        cls._all_trips = dict()

    @classmethod
    def initialize(cls):
        """ Initialize static data structures, once all trips have been created """
        for trip in cls._all_trips.values():
            trip._initialize()

    def _initialize(self):
        """ Perform initialization after all trips have been created """
        # Calculate and cache the list of sorted halts, in sequence order
        h = []
        for hms, halts in self._halts.items():
            for halt in halts:
                h.append((hms, halt))
        h.sort(key=lambda item: item[1].stop_seq)
        self._sorted_halts = h
        # Collect tuples of consecutive stops
        for ix in range(len(h) - 1):
            self._consecutive_stops.add((h[ix][1].stop_id, h[ix + 1][1].stop_id))

    @property
    def trip_id(self):
        return self._id

    @property
    def halts(self):
        """ Returns a dictionary of BusHalts on this trip,
            keyed by arrival time (h, m, s), with each value
            being a list of BusHalt instances """
        return self._halts

    @property
    def stops(self):
        """ Returns a set of stop_ids visited in this trip """
        return self._stops

    def stops_at(self, stop_id):
        """ Return True if this trip includes a stop at the given stop """
        return stop_id in self._stops

    def stops_at_any(self, stop_set):
        """ Return True if this trip includes any stop from the given set """
        return bool(self._stops & stop_set)

    @property
    def sorted_halts(self):
        """ Returns a list of BusHalts on this trip, sorted by stop sequence """
        assert self._sorted_halts is not None
        return self._sorted_halts

    def has_consecutive_stops(self, stop1_id, stop2_id):
        """ Returns True if the trip includes the two given stops,
            consecutively """
        if not stop1_id:
            return self.stops_at(stop2_id)
        if not stop2_id:
            return self.stops_at(stop1_id)
        return (stop1_id, stop2_id) in self._consecutive_stops

    def following_halt(self, stop_id, base_stop_id):
        """ Scan the halts on this trip following the one at base_stop_id,
            looking for stop_id. If found, return the base halt,
            the next halt after it, and the found halt,
            or (None, None, None) otherwise. """
        halts = self._sorted_halts
        for ix, (_, halt) in enumerate(halts):
            if base_stop_id == halt.stop_id:
                # Found the base stop
                break
        else:
            # Did not find the base stop: return None
            return None, None, None
        # Scan subsequent halts for a stop that is in the given set
        ix += 1
        next_halt = halts[ix][1] if ix < len(halts) else None
        while ix < len(halts):
            if stop_id == halts[ix][1].stop_id:
                # Found it: return the base halt and the found halt
                return halt, next_halt, halts[ix][1]
            ix += 1
        return None, None, None

    @property
    def direction(self):
        """ The direction of this trip, '0' or '1' """
        return self._direction

    @property
    def first_stop(self):
        """ The first BusStop visited on this trip """
        return self._first_stop

    @property
    def last_stop(self):
        """ The last BusStop visited on this trip """
        return self._last_stop

    @property
    def start_time(self):
        """ The start time of this trip """
        return self._start_time

    @property
    def end_time(self):
        """ The end time of this trip """
        return self._end_time

    @property
    def route_id(self):
        return self._route_id

    @property
    def route(self):
        return BusRoute.lookup(self._route_id)

    def __str__(self):
        return "{0}: {1} {2} <{3}>".format(
            self._id, self._headsign, self._short_name, self._direction
        )

    @staticmethod
    def lookup(trip_id):
        """ Return a BusTrip having the given id, or None if it doesn't exist """
        return BusTrip._all_trips.get(trip_id)

    def _add_halt(self, halt):
        """ Add a halt to this trip """
        # Index by arrival time
        arrival = halt.arrival_time
        departure = halt.departure_time
        # Note: there may be multiple halts at the same time!
        self._halts[arrival].append(halt)
        if halt.stop_seq == 1:
            # This is the first stop in the trip
            self._first_stop = halt.stop
        elif halt.stop_seq > self._last_stop_seq:
            # This is, so far, the last stop in the trip
            self._last_stop = halt.stop
            self._last_stop_seq = halt.stop_seq
        # Add the stop_id to the set of visited stops
        self._stops.add(halt.stop.stop_id)
        # Note the time span (start and end times) for this trip
        if self._start_time is None or self._start_time > arrival:
            self._start_time = arrival
        if self._end_time is None or self._end_time < departure:
            self._end_time = departure

    @staticmethod
    def add_halt(trip_id, halt):
        """ Add a halt to this trip """
        BusTrip.lookup(trip_id)._add_halt(halt)


class BusService:

    """ A BusService encapsulates a set of trips on a BusRoute that can be
        active on a particular date, as determined by a BusCalendar """

    _all_services = dict()

    def __init__(self, service_id):
        # The service id is a route id + '/' + a nonunique service id
        self._id = service_id
        self._trips = dict()
        self._service = schedule = service_id.split("/")[1]
        # Decode year, month, date
        self._valid_from = date(
            int(schedule[0:4]), int(schedule[4:6]), int(schedule[6:8]),
        )
        # Decode weekday validity of service,
        # M T W T F S S
        self._weekdays = [c != "-" for c in schedule[9:16]]
        # List of trips, ordered by start time
        self._ordered_trips = []
        # Collect all services in a single dict
        BusService._all_services[service_id] = self

    @staticmethod
    def clear():
        """ Clear all services """
        BusService._all_services = dict()

    @staticmethod
    def initialize():
        """ Complete initialization of services and trips """
        for service in BusService._all_services.values():
            service._initialize()

    def _initialize(self):
        """ Complete initialization of this service """
        self._ordered_trips = sorted(
            self._trips.values(), key=lambda trip: trip.start_time
        )

    @staticmethod
    def lookup(service_id):
        """ Get a BusService by its identifier """
        return BusService._all_services.get(service_id) or BusService(service_id)

    @property
    def service_id(self):
        return self._id

    @property
    def trips(self):
        """ The trips associated with this service """
        return self._trips.values()

    def is_active_on_date(self, on_date):
        """ Returns True if the service is active on the given date """
        return (
            # self._valid_from <= on_date and
            # self._weekdays[on_date.weekday()] and
            self._service
            in BusCalendar.lookup(on_date)
        )

    def is_active_on_weekday(self, weekday):
        """ Returns True if the service is active on the given weekday.
            This is currently not reliable. """
        return self._weekdays[weekday]

    def add_trip(self, trip):
        """ Add a trip to this service """
        self._trips[trip.trip_id] = trip


class BusRoute:

    """ A BusRoute has one or more BusServices serving it.
        Each BusService has one or more BusTrips associated with it.
        Each BusTrip involves a number of BusStops, via a number
        of BusHalts. """

    _all_routes = dict()

    def __init__(self, route_id):
        # We store the long-form route_id, i.e. 'ST.1' for route 1
        # in the capital area
        assert "." in route_id
        self._id = route_id
        self._area, self._number = route_id.split(".", maxsplit=2)
        self._services = dict()
        assert route_id not in BusRoute._all_routes, (
            "route_id " + route_id + " already exists"
        )
        BusRoute._all_routes[route_id] = self

    def add_service(self, service):
        """ Add a service to this route """
        self._services[service.service_id] = service

    def active_services(self, on_date):
        """ Returns a list of the services on this route
            that are active on the given date """
        if on_date is None:
            now = datetime.utcnow()
            on_date = date(now.year, now.month, now.day)
        return [s for s in self._services.values() if s.is_active_on_date(on_date)]

    def active_services_today(self):
        """ Returns a list of the services on this route
            that are active today, based on UTC (Icelandic time) """
        return self.active_services(None)

    def __str__(self):
        return "Route {0} with {1} services, of which {2} are active today".format(
            self._id, len(self._services), len(self.active_services_today())
        )

    @property
    def number(self):
        return self._number

    @property
    def area(self):
        return self._area

    @property
    def route_id(self):
        return self._id

    @staticmethod
    def lookup_number(route_number, *, area_priority=_DEFAULT_AREA_PRIORITY):
        """ Return the route having the given number """
        assert "." not in route_number
        for area in area_priority:
            route_id = area + "." + route_number
            route = BusRoute._all_routes.get(route_id)
            if route is not None:
                return route
        return None

    @staticmethod
    def make_id(route_number, *, area_priority=_DEFAULT_AREA_PRIORITY):
        """ Return the full id for the route having the given number, assuming
            the indicated area priority """
        route = BusRoute.lookup_number(route_number, area_priority=area_priority)
        return None if route is None else route.route_id

    @staticmethod
    def lookup(route_id):
        """ Return the route having the given full identifier """
        if route_id is None:
            return None
        assert "." in route_id
        return BusRoute._all_routes.get(route_id)

    @staticmethod
    def all_routes():
        """ Return a dictionary of all routes, keyed by identifier """
        return BusRoute._all_routes

    @staticmethod
    def initialize():
        """ Read information about bus routes from the trips.txt file """
        BusRoute._all_routes = dict()
        BusService.clear()
        BusTrip.clear()
        with open(_RESOURCES_PATH("trips.txt"), "r", encoding="utf-8") as f:
            index = 0
            for line in f:
                index += 1
                if index == 1:
                    # Ignore first line
                    continue
                line = line.strip()
                if not line:
                    continue
                # Format is:
                # route_id,service_id,trip_id,trip_headsign,trip_short_name,
                # direction_id,block_id,shape_id
                f = line.split(",")
                assert len(f) == 8
                # Break 'ST.17' into components area='ST' and number='17'
                route_id = f[0]
                route = BusRoute.lookup(route_id) or BusRoute(route_id)
                # Make a unique service id out of the route id
                # plus the non-unique service id
                service = BusService.lookup(route_id + "/" + f[1])
                route.add_service(service)
                trip = BusTrip(
                    trip_id=f[2],
                    route_id=route_id,
                    headsign=f[3],
                    short_name=f[4],
                    direction=f[5],
                    block=f[6],
                )
                # We don't use shape_id, f[7], for now
                service.add_trip(trip)


class BusStop:

    """ A BusStop is a place at a particular location where one or more
        buses stop on their trips. """

    _all_stops = dict()
    _all_stops_by_name = defaultdict(list)

    def __init__(self, stop_id, name, location):
        self._id = stop_id
        self._name = name
        # Search key for this stop: lowercase, no hyphens or slashes
        self._skey = (
            name.lower().replace("-", " ").replace("/", " ").replace("   ", " ")
        )
        # Location is a tuple of (lat, lon)
        (lat, lon) = self._location = location
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0
        assert stop_id not in BusStop._all_stops
        BusStop._all_stops[stop_id] = self
        BusStop._all_stops_by_name[name].append(self)
        # Dict of routes that visit this stop, with each
        # value being a set of directions
        self._visits = defaultdict(set)

    @staticmethod
    def lookup(stop_id):
        """ Return a BusStop with the given id, or None if no such stop exists """
        return BusStop._all_stops.get(stop_id)

    @staticmethod
    def closest_to(location, n=1, within_radius=None):
        """ Find the bus stop closest to the given location and return it,
            or a list of the closest stops if n > 1, but in any case only return
            stops that are within the given radius (in kilometers). """
        if n < 1:
            return None
        dist = [
            (distance(location, stop.location), stop)
            for stop in BusStop._all_stops.values()
        ]
        if within_radius is not None:
            dist = [(d, stop) for d, stop in dist if d <= within_radius]
        if not dist:
            return None
        # Sort on increasing distance
        dist = sorted(dist, key=lambda t: t[0])
        if n == 1:
            # Only one stop requested: return it
            return dist[0][1]
        # More than one stop requested: return a list
        return [stop for _, stop in dist[0:n]]

    @staticmethod
    def named(name, *, fuzzy=False):
        """ Return all bus stops with the given name,
            optionally using fuzzy matching """
        stops = BusStop._all_stops_by_name.get(name, [])
        if not fuzzy:
            # No fuzzy stuff: we're done
            return stops
        # Continue, this time with fuzzier criteria:
        # match any stop name containing the given string as a
        # whole word, using lower case matching
        # Note the stops we already have in the result list
        stop_ids = set(stop.stop_id for stop in stops)
        nlower = name.lower().replace("-", " ").replace("   ", " ")
        for stop_name, stops in BusStop._all_stops_by_name.items():
            stop = stops[0]
            match = re.search(r"\b" + nlower + r"\b", stop._skey)
            if not match:
                # Try the voice version, if different
                voice_key = _VOICE_NAMES.get(stop_name)
                match = voice_key is not None and re.search(
                    r"\b" + nlower + r"\b", voice_key.lower()
                )
            if not match:
                continue
            stop_ids |= set(stop.stop_id for stop in stops)
        return [BusStop.lookup(stop_id) for stop_id in stop_ids]

    @staticmethod
    def sort_by_proximity(stops, location):
        """ Sort a list of bus stops by increasing distance from the
            given location """
        stops.sort(key=lambda stop: distance(location, stop.location))

    @staticmethod
    def voice(stop_name):
        """ Return a voice-friendly version of bus stop names """
        return _VOICE_NAMES.get(stop_name, stop_name)

    def __str__(self):
        return self._name

    @property
    def stop_id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @property
    def visits(self):
        """ Return the routes that visit this stop, as
            a dict: { route_id : set(directions) } """
        return self._visits

    def is_visited_by_route(self, route_id):
        """ If the given route visits this stop,
            return a set of directions ('0' and/or '1').
            Otherwise, return None. """
        return self._visits.get(route_id)

    @property
    def location(self):
        return self._location

    @staticmethod
    def add_halt(stop_id, halt):
        """ Add a halt to this stop, indexed by arrival time """
        stop = BusStop.lookup(stop_id)
        assert stop is not None
        # Note which routes stop here, and in which directions
        stop._visits[halt.route_id].add(halt.direction)

    @staticmethod
    def initialize():
        """ Read information about bus stops from the stops.txt file """
        BusStop._all_stops = dict()
        BusStop._all_stops_by_name = defaultdict(list)
        with open(_RESOURCES_PATH("stops.txt"), "r", encoding="utf-8") as f:
            index = 0
            for line in f:
                index += 1
                if index == 1:
                    # Ignore first line
                    continue
                line = line.strip()
                if not line:
                    continue
                # Format is:
                # stop_id,stop_name,stop_lat,stop_lon,location_type
                f = line.split(",")
                assert len(f) == 5
                stop_id = f[0].strip()
                assert stop_id not in BusStop._all_stops
                BusStop(
                    stop_id=stop_id,
                    name=f[1].strip(),
                    location=(float(f[2]), float(f[3])),
                )


class BusHalt:

    """ The scheduled arrival and departure of a bus at a particular stop
        on a particular trip """

    def __init__(self, trip_id, arrival_time, stop_id, stop_sequence):
        self._trip_id = trip_id
        self._stop_id = stop_id
        # The sequence number of this stop within its trip
        self._stop_seq = stop_sequence
        # (h, m, s) tuple
        self._arrival_time = arrival_time
        # self._departure_time = departure_time
        # self._pickup_type = pickup_type
        # Create relationships to the trip and to the stop
        BusTrip.add_halt(trip_id, self)
        BusStop.add_halt(stop_id, self)

    def time_to(self, halt):
        """ Return the time, in seconds, between this halt and the given one """
        if halt is self:
            return 0
        today = date.today()
        t1 = datetime.combine(today, time(*self._arrival_time))
        t2 = datetime.combine(today, time(*halt._arrival_time))
        return (t2 - t1).total_seconds()

    @property
    def arrival_time(self):
        return self._arrival_time

    @property
    def departure_time(self):
        return self._arrival_time  # Not presently implemented

    @property
    def stop_seq(self):
        return self._stop_seq

    @property
    def stop_id(self):
        return self._stop_id

    @property
    def stop(self):
        return BusStop.lookup(self._stop_id)

    @property
    def trip(self):
        return BusTrip.lookup(self._trip_id)

    @property
    def route_id(self):
        return self.trip.route_id

    @property
    def direction(self):
        return self.trip.direction

    @staticmethod
    def initialize():
        """ Read information about bus halts from the stop_times.txt file """

        def to_hms(s):
            """ Convert a hh:mm:ss string to a (h, m, s) tuple """
            return (int(s[0:2]), int(s[3:5]), int(s[6:8]))

        with open(_RESOURCES_PATH("stop_times.txt"), "r", encoding="utf-8") as f:
            index = 0
            for line in f:
                index += 1
                if index == 1:
                    # Ignore first line
                    continue
                line = line.strip()
                if not line:
                    continue
                # Format is:
                # trip_id,arrival_time,departure_time,stop_id,
                # stop_sequence,stop_headsign,pickup_type
                f = line.split(",")
                assert len(f) == 7
                BusHalt(
                    f[0].strip(),  # trip_id
                    to_hms(f[1].strip()),  # arrival_time
                    # to_hms(f[2].strip()),  # departure_time
                    f[3].strip(),  # stop_id
                    int(f[4]),  # stop_sequence
                    # Ignore stop_headsign
                )


class Bus:

    """ The Bus class represents the current state of a bus,
        including its route identifier, its location and
        heading, its last or current stop, its next stop,
        and its status code. """

    _all_buses = defaultdict(list)
    _timestamp = None
    _lock = threading.Lock()

    def __init__(
        self, *, route_id, stop_id, next_stop_id, location, heading, code, timestamp
    ):
        assert "." in route_id
        self._route_id = route_id
        self._stop_id = stop_id
        self._next_stop_id = next_stop_id
        # Location is a tuple of (lat, lon)
        (lat, lon) = self._location = location
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0
        self._heading = heading
        self._code = code
        self._timestamp = timestamp
        Bus._all_buses[route_id].append(self)

    @staticmethod
    def all_buses():
        """ Returns a dict of lists of all known buses, keyed by route id """
        Bus.refresh_state()
        return Bus._all_buses

    @staticmethod
    def buses_on_route(route_id):
        """ Return all buses currently driving on the indicated route """
        Bus.refresh_state()
        return Bus._all_buses[route_id]

    @staticmethod
    def _fetch_state():
        """ Fetch new state via HTTP """
        r = requests.get(_STATUS_URL) if _STATUS_URL else None
        # pylint: disable=no-member
        if r is not None and r.status_code == requests.codes.ok:
            html_doc = r.text
            return ET.fromstring(html_doc)
        # State not available
        return None

    @staticmethod
    def _read_state():
        """ As a fallback, attempt to read bus real-time data from status file """
        try:
            return ET.parse(_STATUS_FILE).getroot()
        except FileNotFoundError:
            return None

    @staticmethod
    def _load_state():
        """ Loads a fresh state of all buses from the web """
        # Clear previous state
        Bus._all_buses = defaultdict(list)
        # Attempt to fetch state via HTTP
        root = Bus._fetch_state()
        if root is None:
            # Fall back to reading state from file
            root = Bus._read_state()
        if root is None:
            # State is not available
            return
        for bus in root.findall("bus"):
            ts = bus.get("time")
            ts = datetime(
                year=2000 + int(ts[0:2]),
                month=int(ts[2:4]),
                day=int(ts[4:6]),
                hour=int(ts[6:8]),
                minute=int(ts[8:10]),
                second=int(ts[10:12]),
            )
            lat = float(bus.get("lat"))
            lon = float(bus.get("lon"))
            heading = float(bus.get("head"))
            route_id = bus.get("route")
            # Convert area indicators
            # !!! TODO: This needs to be verified further, and the 'SA' area added
            if route_id.startswith("A"):
                route_id = "AF." + route_id[1:]
            elif route_id.startswith("R"):
                route_id = "RY." + route_id[1:]
            else:
                assert route_id[0] in "123456789"
                # Assume capital area
                route_id = "ST." + route_id
            stop_id = bus.get("stop")
            next_stop_id = bus.get("next")
            code = int(bus.get("code"))
            Bus(
                route_id=route_id,
                location=(lat, lon),
                stop_id=stop_id,
                next_stop_id=next_stop_id,
                heading=heading,
                code=code,
                timestamp=ts,
            )
        Bus._timestamp = datetime.utcnow()

    @staticmethod
    def refresh_state():
        """ Load a new state, if required """
        with Bus._lock:
            if Bus._timestamp is not None:
                delta = datetime.utcnow() - Bus._timestamp
                if delta.total_seconds() < _REFRESH_INTERVAL:
                    # The state that we already have is less than
                    # _REFRESH_INTERVAL seconds old: no need to refresh
                    return
            Bus._load_state()

    @property
    def route_id(self):
        return self._route_id

    @property
    def route(self):
        return BusRoute.lookup(self._route_id)

    @property
    def location(self):
        return self._location

    @property
    def heading(self):
        return self._heading

    @property
    def stop_id(self):
        return self._stop_id

    @property
    def next_stop_id(self):
        return self._next_stop_id

    @property
    def stop(self):
        return BusStop.lookup(self._stop_id)

    @property
    def next_stop(self):
        return BusStop.lookup(self._next_stop_id)

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def code(self):
        """ Bus state """
        # 1 Ekki notað
        # 2 Vagninn hefur stöðvað
        # 3 Vagninn hefur ekið af stað
        # 4 Höfuðrofi af
        #   Vagninn er ekki ræstur. Skeyti berast nú á tveggja mínútna fresti frá vagni með þessum ástæðukóða.
        # 5 Höfuðrofi settur á
        #   Vagninn ræstur. Skeyti berast nú á 15 sekúndna fresti frá vagni.
        # 6 Vagn í gangi og liðnar amk 15 sek frá síðasta skeyti.
        # 7 Komið á stöð
        return self._code

    @property
    def state(self):
        """ Return the entire state in one call """
        return (
            self._route_id,
            self._location,
            self._heading,
            self.stop,
            self.next_stop,
            self._code,
            self._timestamp,
        )


class BusSchedule:

    """ This class constructs a bus schedule for a particular date, by default today,
        which can then be queried. """

    def __init__(self, for_date=None):
        """ Create a schedule for today: Route, stop, time """
        s = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        if for_date is None:
            now = datetime.utcnow()
            for_date = date(now.year, now.month, now.day)
        self._for_date = for_date
        for route in BusRoute.all_routes().values():
            for service in route.active_services(on_date=for_date):
                for trip in service.trips:
                    for hms, halt in trip.sorted_halts:
                        s[route.route_id][trip.last_stop.name][halt.stop.name].append(
                            hms
                        )
        self._sched = s

    @property
    def date(self):
        return self._for_date

    @property
    def is_valid_today(self):
        """ Return True if this schedule is valid for today """
        now = datetime.utcnow()
        return self._for_date == date(now.year, now.month, now.day)

    def print_schedule(self, route_id):
        """ Print a schedule for a given route """
        print("Áætlun leiðar {0:2}".format(route_id))
        print("----------------")
        s = self._sched[route_id]
        for direction, halts in s.items():
            print("Átt: {0}".format(direction))
            for stop_name, times in halts.items():
                print("   Stöð: {0}".format(stop_name))
                col = 0
                for hms in sorted(times):
                    if col == 8:
                        print()
                        col = 0
                    if col == 0:
                        print("     ", end="")
                    print(" {0:02}:{1:02}".format(hms[0], hms[1]), end="")
                    col += 1
                print()
        print("\n\n")

    def arrivals(
        self,
        route_number,
        stop,
        *,
        n=2,
        after_hms=None,
        area_priority=_DEFAULT_AREA_PRIORITY
    ):
        """ Return a list of the subsequent arrivals of buses on the
            given route at the indicated stop, with reference to the
            given timepoint, or the current time if None. Also returns
            a boolean indicating whether the bus arrives at all at this
            stop today. """
        # h is a list of halts for each direction
        h = defaultdict(list)
        route_id = BusRoute.make_id(route_number, area_priority=area_priority)
        arrives = False
        if route_id is None:
            return h, arrives
        if after_hms is None:
            now = datetime.utcnow()
            after_hms = (now.hour, now.minute, now.second)
        s = self._sched[route_id]
        for direction, halts in s.items():
            for halt_stop_name, times in halts.items():
                if halt_stop_name == stop.name:
                    # Note that the bus arrives at some point today,
                    # according to the schedule
                    arrives = True
                    # Don't include halts at final stops in the direction
                    # of that same stop
                    if halt_stop_name != direction:
                        # Only include halts that occcur after the requested time
                        hlist = [hms for hms in times if hms >= after_hms]
                        if hlist:
                            h[direction] += hlist
        for direction, arrival_times in h.items():
            # Return the first N subsequent arrival times
            # for each direction
            h[direction] = sorted(arrival_times)[:n]
        return h, arrives

    def predicted_arrival(
        self, route_number, stop, *, area_priority=_DEFAULT_AREA_PRIORITY
    ):
        """ Predicts when the next bus will arrive on route route_id
            at stop stop_name. """

        # The function attempts to predict the arrival time, at a particular
        # stop, of the next bus on a given route. It does so by inference from
        # the real-time data available from straeto.is about bus positions and
        # movements. The data includes the last (lat, lon) location of the bus,
        # the last stop visited, the next stop to be visited, and the route the bus
        # is on, among other things. The challenge is to reconcile this data
        # with the bus schedule to find out which trip the bus is likely to be on,
        # and from there to infer a likely arrival time as a sum of the time
        # left on the current segment (last stop -> next stop) plus the time
        # it will take to drive from the next stop to the stop being queried,
        # according to the schedule. We thus assume that the bus will neither be
        # further delayed, nor make up for previous delays, when driving the
        # distance from its next stop to the queried stop.

        route_id = BusRoute.make_id(route_number, area_priority=area_priority)
        route = BusRoute.lookup(route_id)
        if route is None:
            return None

        # Establish the current time in h:m:s format
        now = datetime.utcnow()
        today = date.today()
        after_hms = (now.hour, now.minute, now.second)
        # Find the trip that is closest to the current time
        closest_trip = dict()
        closest_gap = dict()

        def gap(trip):
            def diff(hms1, hms2):
                """ Return the number of seconds between the two (h, m, s) tuples """
                if hms1[0] >= 24:
                    # Apparently, some arrival times can exceed 23 hours,
                    # so we must account for that (since Python doesn't)
                    t1 = datetime.combine(
                        today + timedelta(days=1), time(hms1[0] - 24, hms1[1], hms1[2])
                    )
                else:
                    t1 = datetime.combine(today, time(*hms1))
                if hms2[0] >= 24:
                    t2 = datetime.combine(
                        today + timedelta(days=1), time(hms2[0] - 24, hms2[1], hms2[2])
                    )
                else:
                    t2 = datetime.combine(today, time(*hms2))
                return (t2 - t1).total_seconds()

            if trip.start_time > after_hms:
                # The trip has not yet started: we won't use it as a basis
                # for prediction, since it is possible that a bus may start
                # the trip at the correct time even if it doesn't show up in
                # the real-time data
                return -1
            elif trip.end_time < after_hms:
                # The trip should be already completed, but we include it
                # anyway, since we may have late buses still on it
                return diff(trip.end_time, after_hms)
            # The trip is underway
            return 0

        for service in route.active_services_today():
            for trip in service.trips:
                # Only include trips that stop at the queried stop(s)
                if trip.stops_at(stop.stop_id):
                    g = gap(trip)
                    if g >= 0:
                        cg = closest_gap.get(trip.direction)
                        if cg is None or g < cg:
                            # This trip is closer to the current time
                            closest_gap[trip.direction] = g
                            closest_trip[trip.direction] = trip

        # If there are no trips to match the buses with, give up
        if not closest_trip:
            return None

        # Now, we have a list of trips that stop at the queried stop
        # and that are undertaken immediately before or during
        # the current time. The list contains both trip directions.
        # The next step is to fetch the real-time status of all buses
        # on the requested route.
        trips = list(closest_trip.values())
        buses = Bus.buses_on_route(route_id)
        result = dict()
        for bus in buses:
            # For each currently active bus, find the trips that are in
            # a direction that matches its last and next stops, and that
            # will subsequently stop at the queried stop.
            bus_stop_tuple = (bus.stop_id, bus.next_stop_id)
            bus_stop = BusStop.lookup(bus.stop_id)
            next_stop = BusStop.lookup(bus.next_stop_id)
            # Calculate the distance between the last stop and the next
            # stop of the bus, as the crow flies
            if bus_stop is not None and next_stop is not None:
                d_stops = distance(bus_stop.location, next_stop.location)
            else:
                d_stops = 0.0
            # Calculate the distance between the bus and the next stop,
            # as the crow flies
            if next_stop is not None:
                d_bus = distance(bus.location, next_stop.location)
            else:
                d_bus = 0.0
            # Approximate the time it would take for the bus to drive
            # from its current location to the next stop, as a ratio
            # of the total scheduled time between the stops
            if d_stops < 0.001:
                # The stops are very close to each other:
                # assume the time to go between them is zero
                d_ratio = 0.0
            else:
                # The ratio can never be larger than 1.0
                d_ratio = min(d_bus / d_stops, 1.0)
            for trip in trips:
                # Check whether this trip includes stops that match the
                # last and next stops of the bus
                if not trip.has_consecutive_stops(*bus_stop_tuple):
                    continue
                # Check whether the stop we want is a subsequent stop for the bus
                last_halt, next_halt, our_halt = trip.following_halt(
                    stop.stop_id, bus.stop_id
                )
                if our_halt is None:
                    continue
                # For this trip, we now have the halt that matches the last stop
                # of the bus, as well as the halt at the queried stop.
                journey_time = last_halt.time_to(
                    next_halt
                ) * d_ratio + next_halt.time_to(our_halt)
                estimated_arrival = bus.timestamp + timedelta(seconds=journey_time)
                if estimated_arrival < now:
                    # This bus is estimated to have already arrived and left
                    continue
                # We have a potentially usable result: if the arrival is closer than
                # the previously stored one (if any), we accept it
                if _DEBUG:
                    print(
                        "Predicting that the bus at ({0:.6f}, {1:.6f}) will take "
                        "{2:.1f} seconds to drive from {3} to {4}, and then "
                        "{5:.1f} seconds from there to {6}, arriving at {7}".format(
                            *bus.location,
                            last_halt.time_to(next_halt) * d_ratio,
                            last_halt.stop.name,
                            next_halt.stop.name,
                            next_halt.time_to(our_halt),
                            our_halt.stop.name,
                            estimated_arrival
                        )
                    )
                direction = trip.last_stop.name
                if direction not in result or estimated_arrival < result[direction]:
                    result[direction] = estimated_arrival

        if not result:
            return None

        # The result dict is compatible with BusSchedule.arrivals(),
        # and contains entries for directions where each entry has a list of hms tuples
        # (in this case only one hms tuple for each direction)

        # Note: we round the arrival time down, so 17:35:50 becomes 17:35:00 -
        # this is to reduce the risk of missing the bus!
        return {
            direction: [round_to_hh_mm(ts, round_down=True)]
            for direction, ts in result.items()
        }


def print_closest_stop(location):
    """ Answers the query: 'what is the closest bus stop' """
    s = BusStop.closest_to(location)
    print("Bus stop closest to {0} is {1}".format(location, s.name))
    print("The distance to it is {0:.1f} km".format(distance(location, s.location)))


def print_next_arrivals(schedule, location, route_number):
    """ Answers the query: 'when does bus X arrive?' at a given location
        or bus stop name """
    if isinstance(location, tuple):
        stop = BusStop.closest_to(location)
        print("Bus stop closest to {0} is {1}".format(location, stop.name))
    else:
        assert isinstance(location, str)
        stops = BusStop.named(location, fuzzy=True)
        stop = stops[0] if stops else None
        if stop is None:
            print("Can't find a bus stop named {0}".format(location))
            return
    print("Next arrivals of route {0} at {1} are:".format(route_number, stop.name))
    arrivals, _ = schedule.arrivals(route_number, stop)
    for direction, times in arrivals.items():
        print(
            "   Direction {0}: {1}".format(
                direction,
                ", ".join("{0:02}:{1:02}".format(hms[0], hms[1]) for hms in times),
            )
        )
    p = schedule.predicted_arrival(route_number, stop)
    if p is None:
        print(
            "Unable to predict the next arrival of route {0} at {1}".format(
                route_number, stop.name
            )
        )
    else:
        print(
            "Next predicted arrival of route {0} at {1} is:".format(
                route_number, stop.name
            )
        )
        for direction, times in p.items():
            print(
                "   Direction {0}: {1}".format(
                    direction,
                    ", ".join("{0:02}:{1:02}".format(hms[0], hms[1]) for hms in times),
                )
            )


def initialize():
    """ (Re-)initialize all schedule data from text files in the
        resources/ subdirectory """
    # Read stops.txt
    BusStop.initialize()
    # Read calendar_dates.txt
    BusCalendar.initialize()
    # Read trips.txt
    BusRoute.initialize()
    # Read stop_times.txt
    BusHalt.initialize()
    # Initialize the BusTrip instances
    BusTrip.initialize()
    # Initialize the BusService instances
    BusService.initialize()


def fetch_gtfs():
    """ Download the GTFS.zip file and unpack it in the resources/ subdirectory """
    res_path = _RESOURCES_PATH()
    # The resources/ subdirectory must be writable so we can fetch
    # the ZIP archive and unzip it there
    if not os.access(res_path, os.W_OK | os.X_OK):
        msg = "The '{0}' directory must be writable".format(res_path)
        logging.error(msg)
        raise RuntimeError(msg)
    # Fetch the bus schedule information from the open URL
    try:
        with requests.get(_SCHEDULE_URL, stream=True) as r:
            with open(_GTFS_PATH, "wb") as f:
                # This is an efficient method to copy file-like streams
                shutil.copyfileobj(r.raw, f)
    except OSError as e:
        # Something is wrong; unable to fetch
        logging.warning(
            "Exception {2} when trying to download from {0} to {1}".format(
                _SCHEDULE_URL, _GTFS_PATH, e
            )
        )
        return False
    if r.status_code != 200:
        # Something is wrong; unable to fetch
        logging.warning(
            "HTTP status {1} when trying to download from {0}".format(
                _SCHEDULE_URL, r.status_code
            )
        )
        return False
    # Successfully downloaded the ZIP archive: extract all files from it
    with zipfile.ZipFile(_GTFS_PATH, "r") as z:
        z.extractall(res_path)
    return True


def refresh(*, if_older_than=None, re_initialize=False):
    """ Attempt to fetch the most recent GTFS.zip file from the Straeto
        open data source, and reinitialize the already loaded schedule
        data if requested. if_older_than is given in hours, with None
        being interpreted as zero. """

    if if_older_than:
        # Skip the initialization if we already have a recent enough ZIP file
        try:
            tm_time = os.path.getmtime(_GTFS_PATH)
        except IOError:
            # No such file: skip through to the initialization
            pass
        else:
            now = datetime.utcnow()
            ts_file = datetime.fromtimestamp(tm_time)
            if now - ts_file <= timedelta(hours=if_older_than):
                # File is younger than if_older_than: no need to refresh
                return False

    if not fetch_gtfs():
        # Not able to fetch the GTFS.zip archive
        return False

    # Successfully fetched and unzipped a new archive
    if re_initialize:
        initialize()

    # Return True to indicate that the refresh was completed
    return True


# When this module is imported, its data is initialized from the text files
# in the resources/ subdirectory. Subsequently, you may call refresh() to
# refresh the text files from the Straeto open data source.

if __name__ != "__main__":

    initialize()

else:

    import argparse

    parser = argparse.ArgumentParser(
        description="A Python wrapper for the bus schedules of Straeto bs"
    )

    parser.add_argument("--quiet", action="store_true", help="suppress output")

    subparsers = parser.add_subparsers(help="subcommand")

    parser_refresh = subparsers.add_parser(
        "refresh", help="refresh schedule data from Straeto bs website"
    )

    parser_refresh.add_argument(
        "--if_older_than",
        nargs="?",
        type=int,
        default=0,
        help="refresh only if existing GTFS.ZIP file is older than N hours",
    )

    parser_test = subparsers.add_parser("test", help="run test code")

    args = parser.parse_args()

    if hasattr(args, "if_older_than"):
        # This must be the refresh command
        if refresh(if_older_than=args.if_older_than):
            if not args.quiet:
                print("Refresh completed")
        else:
            if not args.quiet:
                print("Refresh was not necessary or not successful")
        import sys

        sys.exit(0)

    # This must be the 'test' command

    initialize()

    # This main program contains a mix of test and demo cases.
    # Normally you use Straeto as a module through import, not as a main program.

    if False:
        # 'Hvar er næsta stoppistöð?'
        print_closest_stop(_MIDEIND_LOCATION)

    sched_today = BusSchedule()

    if False:
        # Examples of queries for next halts of particular routes at particular stops
        # 'Hvenær kemur strætó númer 14?'
        print_next_arrivals(sched_today, _MIDEIND_LOCATION, "14")
        print_next_arrivals(sched_today, "Grunnslóð", "14")
        print_next_arrivals(sched_today, "Grandagarður", "14")
        print_next_arrivals(sched_today, "Mýrargata", "14")

    if True:
        # Print today's schedule for a route
        sched_today.print_schedule("ST.3")

    if False:
        # Dump the schedule data for all routes
        for route in BusRoute.all_routes().values():
            print("{0}:".format(route))
            for service in route.active_services_today():
                print("   service {0}".format(service.service_id))
                for trip in service.trips:
                    print("      trip {0}".format(trip.trip_id))
                    for hms, halt in trip.sorted_halts:
                        print(
                            "         halt {0:02}:{1:02}:{2:02} at {3}".format(
                                hms[0], hms[1], hms[2], halt.stop.name
                            )
                        )

    if True:
        # Dump the real-time locations of all buses
        # all_buses = Bus.all_buses().items()
        all_buses = [("ST.14", Bus.buses_on_route("ST.14"))]
        for route_id, val in sorted(all_buses, key=lambda b: b[0].rjust(2)):
            route = BusRoute.lookup(route_id)
            print("{0}:".format(route))
            for service in route.active_services_today():
                print("   service {0}".format(service.service_id))
            for bus in sorted(val, key=lambda bus: entf(bus.location)):
                print(
                    "   {6} loc:{0}, head:{1:>6.2f}, stop:{2}, next:{3}, code:{4}, "
                    "dist:{5:.2f}".format(
                        locfmt(bus.location),
                        bus.heading,
                        bus.stop,
                        bus.next_stop,
                        bus.code,
                        entf(bus.location),
                        bus.timestamp,
                    )
                )

        print_next_arrivals(sched_today, _MIDEIND_LOCATION, "14")
