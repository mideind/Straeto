"""

    straeto.py: A package encapsulating information about Icelandic buses and bus routes

    Copyright (c) 2019 Miðeind ehf.
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
from datetime import date, datetime
import threading
import functools
from collections import defaultdict
import xml.etree.ElementTree as ET

import requests


_THIS_PATH = os.path.dirname(__file__) or "."
# Where the URL to fetch bus status data is stored (this is not public information;
# you must apply to Straeto bs to obtain permission and get your own URL)
_STATUS_URL_FILE = os.path.join(_THIS_PATH, "config", "status_url.txt")
try:
    _STATUS_URL = open(_STATUS_URL_FILE, "r").read().strip()
except FileNotFoundError:
    _STATUS_URL = None
# Fallback location to fetch status info from, if not available via HTTP
_STATUS_FILE = os.path.join(_THIS_PATH, "resources", "status.xml")
_EARTH_RADIUS = 6371.0088  # Earth's radius in km
_MIDEIND_LOCATION = (64.156896, -21.951200)  # Fiskislóð 31, 101 Reykjavík


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
        slat * slat +
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
        slon * slon
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS * c


# Entfernung - used for test purposes
entf = functools.partial(distance, _MIDEIND_LOCATION)


def locfmt(loc):
    """ Return a (lat, lon) location tuple in a standard string format """
    return "({0:.6f},{1:.6f})".format(loc[0], loc[1])


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
        with open(
            os.path.join(_THIS_PATH, "resources", "calendar_dates.txt"),
            "r",
        ) as f:
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

    def __init__(self, **kwargs):
        self._id = kwargs.pop("trip_id")
        self._route_id = kwargs.pop("route_id")
        self._headsign = kwargs.pop("headsign")
        self._short_name = kwargs.pop("short_name")
        self._direction = kwargs.pop("direction")
        self._block = kwargs.pop("block")
        self._halts = dict()
        # Cache a sorted list of halts and arrival times for this trip
        self._sorted_halts = None
        # Store the first and last stop ids for this trip
        self._first_stop = None
        self._last_stop_seq = 0
        self._last_stop = None
        # Accumulate a singleton database of all trips
        BusTrip._all_trips[self._id] = self

    @property
    def id(self):
        return self._id

    @property
    def halts(self):
        """ Returns a dictionary of BusHalts on this trip,
            keyed by arrival time (h, m, s) """
        return self._halts

    @property
    def sorted_halts(self):
        """ Returns a list of BusHalts on this trip, sorted by arrival time (h:m:s) """
        # We only calculate the list of sorted halts once, then cache it
        if self._sorted_halts is None:
            self._sorted_halts = sorted(self._halts.items(), key=lambda h:h[0])
        return self._sorted_halts

    @property
    def direction(self):
        """ The direction of this trip, '0' or '1' """
        return self._direction

    @property
    def last_stop(self):
        """ The last BusStop visited on this trip """
        return self._last_stop

    @property
    def first_stop(self):
        """ The first BusStop visited on this trip """
        return self._first_stop

    @property
    def route_id(self):
        return self._route_id

    @property
    def route(self):
        return BusRoute.lookup(self._route_id)

    def __str__(self):
        return (
            "{0}: {1} {2} <{3}>"
            .format(self._id, self._headsign, self._short_name, self._direction)
        )

    @staticmethod
    def lookup(trip_id):
        """ Return a BusTrip having the given id, or None if it doesn't exist """
        return BusTrip._all_trips.get(trip_id)

    def _add_halt(self, halt):
        """ Add a halt to this trip """
        # Index by arrival time
        self._halts[halt.arrival_time] = halt
        if halt.stop_seq == 1:
            # This is the first stop in the trip
            self._first_stop = halt.stop
        elif halt.stop_seq > self._last_stop_seq:
            # This is, so far, the last stop in the trip
            self._last_stop = halt.stop
            self._last_stop_seq = halt.stop_seq

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
            int(schedule[0:4]),
            int(schedule[4:6]),
            int(schedule[6:8]),
        )
        # Decode weekday validity of service,
        # M T W T F S S
        self._weekdays = [
            c != "-" for c in schedule[9:16]
        ]
        BusService._all_services[service_id] = self

    @staticmethod
    def lookup(service_id):
        """ Get a BusService by its identifier """
        return BusService._all_services.get(service_id) or BusService(service_id)

    @property
    def id(self):
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
            self._service in BusCalendar.lookup(on_date)
        )

    def is_active_on_weekday(self, weekday):
        """ Returns True if the service is active on the given weekday.
            This is currently not reliable. """
        return self._weekdays[weekday]

    def add_trip(self, trip):
        """ Add a trip to this service """
        self._trips[trip.id] = trip


class BusRoute:

    """ A BusRoute has one or more BusServices serving it.
        Each BusService has one or more BusTrips associated with it.
        Each BusTrip involves a number of BusStops, via a number
        of BusHalts. """

    _all_routes = dict()

    def __init__(self, route_id):
        self._id = route_id
        self._services = dict()
        BusRoute._all_routes[route_id] = self

    def add_service(self, service):
        """ Add a service to this route """
        self._services[service.id] = service

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
        return (
            "Route {0} with {1} services, of which {2} are active today"
            .format(self._id, len(self._services), len(self.active_services_today()))
        )

    @property
    def id(self):
        return self._id

    @staticmethod
    def lookup(route_id):
        """ Return the route having the given identifier """
        return BusRoute._all_routes.get(route_id) or BusRoute(route_id)

    @staticmethod
    def all_routes():
        """ Return a dictionary of all routes, keyed by identifier """
        return BusRoute._all_routes

    @staticmethod
    def initialize():
        """ Read information about bus routes from the trips.txt file """
        BusRoute._all_routes = dict()
        with open(os.path.join(_THIS_PATH, "resources", "trips.txt"), "r") as f:
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
                # Convert 'ST.17' to '17'
                route_id = f[0].split(".")[1]
                route = BusRoute.lookup(route_id)
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
        # Location is a tuple of (lat, lon)
        (lat, lon) = self._location = location
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0
        # Maintain a dictionary of halts at this stop,
        # indexed by arrival time
        self._halts = dict()
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
        dist = sorted(dist, key=lambda t:t[0])
        if n == 1:
            # Only one stop requested: return it
            return dist[0][1]
        # More than one stop requested: return a list
        return [stop for _, stop in dist[0:n]]

    @staticmethod
    def named(name, *, fuzzy=False):
        """ Return all bus stops with the given name """
        stops = BusStop._all_stops_by_name.get(name, [])
        if not fuzzy:
            return stops
        # Continue, this time with fuzzier criteria:
        # match any stop name containing the given string as a
        # whole word, using lower case matching
        nlower = name.lower()
        for key, val in BusStop._all_stops_by_name.items():
            if re.search(r"\b" + nlower + r"\b", key.lower()):
                stops.extend(val)
        return stops

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
        stop._halts[halt.arrival_time] = halt
        # Note which routes stop here, and in which directions
        stop._visits[halt.route_id].add(halt.direction)

    @staticmethod
    def initialize():
        """ Read information about bus stops from the stops.txt file """
        with open(os.path.join(_THIS_PATH, "resources", "stops.txt"), "r") as f:
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
                    location=(float(f[2]), float(f[3]))
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

    @property
    def arrival_time(self):
        return self._arrival_time

    @property
    def stop_seq(self):
        return self._stop_seq

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

        with open(os.path.join(_THIS_PATH, "resources", "stop_times.txt"), "r") as f:
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
                # trip_id,arrival_time,departure_time,stop_id,stop_sequence,stop_headsign,pickup_type
                f = line.split(",")
                assert len(f) == 7
                BusHalt(
                    f[0].strip(),  # trip_id
                    to_hms(f[1].strip()),  # arrival_time
                    # to_hms(f[2].strip()),  # departure_time
                    f[3].strip(),  # stop_id
                    int(f[4]),  # stop_sequence
                    # Ignore stop_headsign (seems to be always empty)
                    # f[6].strip(),  # pickup_type
                )


class Bus:

    """ The Bus class represents the current state of a bus,
        including its route identifier, its location and
        heading, its last or current stop, its next stop,
        and its status code. """

    _all_buses = defaultdict(list)
    _timestamp = None
    _lock = threading.Lock()

    def __init__(self, **kwargs):
        self._route_id = kwargs.pop("route_id")
        self._stop = kwargs.pop("stop")
        self._next_stop = kwargs.pop("next_stop")
        # Location is a tuple of (lat, lon)
        (lat, lon) = self._location = kwargs.pop("location")
        assert -90.0 <= lat <= 90.0
        assert -180.0 <= lon <= 180.0
        self._heading = kwargs.pop("heading")
        self._code = kwargs.pop("code")
        self._timestamp = kwargs.pop("timestamp")
        Bus._all_buses[self._route_id].append(self)

    @staticmethod
    def all_buses():
        """ Returns a dict of lists of all known buses, keyed by route id """
        Bus.refresh_state()
        return Bus._all_buses

    @staticmethod
    def buses_on_route(route_id):
        Bus.refresh_state()
        return Bus._all_buses[route_id]

    @staticmethod
    def _fetch_state():
        """ Fetch new state via HTTP """
        r = requests.get(_STATUS_URL) if _STATUS_URL else None
        # pylint: disable=no-member
        if r is not None and r.status_code == requests.codes.ok:
            # print(f"Successfully fetched state from {_STATUS_URL}")
            html_doc = r.text
            return ET.fromstring(html_doc)
        # State not available
        return None

    @staticmethod
    def _read_state():
        """ As a fallback, attempt to read bus real-time data from status file """
        # print(f"Reading state from {_STATUS_FILE}")
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
        for bus in root.findall('bus'):
            ts = bus.get('time')
            ts = datetime(
                year=2000 + int(ts[0:2]),
                month=int(ts[2:4]),
                day=int(ts[4:6]),
                hour=int(ts[6:8]),
                minute=int(ts[8:10]),
                second=int(ts[10:12]),
            )
            lat = float(bus.get('lat'))
            lon = float(bus.get('lon'))
            heading = float(bus.get('head'))
            route_id = bus.get('route')
            stop = bus.get('stop')
            next_stop = bus.get('next')
            code = int(bus.get('code'))
            Bus(
                route_id=route_id,
                location=(lat, lon),
                stop=stop,
                next_stop=next_stop,
                heading=heading,
                code=code,
                timestamp=ts
            )
        Bus._timestamp = datetime.utcnow()

    @staticmethod
    def refresh_state():
        """ Load a new state, if required """
        with Bus._lock:
            if Bus._timestamp is not None:
                delta = datetime.utcnow() - Bus._timestamp
                if delta.total_seconds() < 60:
                    # The state that we already have is less than
                    # a minute old: no need to refresh
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
    def stop(self):
        return BusStop.lookup(self._stop)

    @property
    def next_stop(self):
        return BusStop.lookup(self._next_stop)

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
            BusStop.lookup(self._stop),
            BusStop.lookup(self._next_stop),
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
                        s[route.id][trip.last_stop.name][halt.stop.name].append(hms)
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

    def arrivals(self, route_id, stop_name, *, n=2, after_hms=None):
        """ Return a list of the subsequent arrivals of buses on the
            given route at the indicated stop, with reference to the
            given timepoint, or the current time if None. """
        if after_hms is None:
            now = datetime.utcnow()
            after_hms = (now.hour, now.minute, now.second)
        s = self._sched[route_id]
        # h is a list of halts for each direction
        h = defaultdict(list)
        for direction, halts in s.items():
            for halt_stop_name, times in halts.items():
                if halt_stop_name == stop_name:
                    h[direction] += [hms for hms in times if hms >= after_hms]
        for direction, arrival_times in h.items():
            # Return the first N subsequent arrival times
            # for each direction
            h[direction] = sorted(arrival_times)[:n]
        return h


def print_closest_stop(location):
    """ Answers the query: 'what is the closest bus stop' """
    s = BusStop.closest_to(location)
    print("Bus stop closest to {0} is {1}".format(location, s.name))
    print(
        "The distance to it is {0:.1f} km"
        .format(distance(location, s.location))
    )


def print_next_arrivals(schedule, location, route_id):
    """ Answers the query: 'when does bus X arrive?' at a given location
        or bus stop name """
    if isinstance(location, tuple):
        s = BusStop.closest_to(location)
        stop_name = s.name
        print("Bus stop closest to {0} is {1}".format(location, stop_name))
    else:
        stop_name = location
    print("Next arrivals of route {0} at {1} are:".format(route_id, stop_name))
    for direction, times in schedule.arrivals(route_id, stop_name).items():
        print(
            "   Direction {0}: {1}"
            .format(
                direction,
                ", ".join(
                    "{0:02}:{1:02}".format(hms[0], hms[1]) for hms in times
                )
            )
        )


# When importing this module, initialize its data from the text files
# in the resources/ subdirectory
BusStop.initialize()
BusCalendar.initialize()
BusRoute.initialize()
BusHalt.initialize()


if __name__ == "__main__":

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
        sched_today.print_schedule("12")

    if False:
        # Dump the schedule data for all routes
        for route in BusRoute.all_routes().values():
            print("{0}:".format(route))
            for service in route.active_services_today():
                print("   service {0}".format(service.id))
                for trip in service.trips:
                    print("      trip {0}".format(trip.id))
                    for hms, halt in trip.sorted_halts:
                        print(
                            "         halt {0:02}:{1:02}:{2:02} at {3}"
                            .format(hms[0], hms[1], hms[2], halt.stop.name)
                        )

    if False:
        # Dump the real-time locations of all buses
        all_buses = Bus.all_buses().items()
        for route_id, val in sorted(all_buses, key=lambda b: b[0].rjust(2)):
            route = BusRoute.lookup(route_id)
            print("{0}:".format(route))
            for service in route.active_services_today():
                print("   service {0}".format(service.id))
            for bus in sorted(val, key=lambda bus: entf(bus.location)):
                print(
                    "   location:{0}, head:{1:>6.2f}, stop:{2}, next:{3}, code:{4}, "
                    "distance:{5:.2f}"
                    .format(
                        locfmt(bus.location), bus.heading, bus.stop,
                        bus.next_stop, bus.code, entf(bus.location)
                    )
                )
