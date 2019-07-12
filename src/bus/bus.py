"""

    Bus: A package encapsulating information about buses and bus routes

    Bus and BusStop classes

    Copyright (c) 2019 Miðeind ehf.
    Author: Vilhjálmur Þorsteinsson

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


    This module implements the Bus and BusStop classes.

"""

import datetime
from collections import defaultdict


class Bus:

    _all_buses = None

    def __init__(self, **kwargs):
        self._route_id = kwargs.pop("route_id")
        self._stop = kwargs.pop("stop")
        self._next_stop = kwargs.pop("next_stop")
        self._location = kwargs.pop("location")
        self._heading = kwargs.pop("heading")
        Bus._all_buses[route_id].append(self)

    @staticmethod
    def all_buses():
        """ Returns a dict of lists of all known buses, keyed by route id """
        return Bus._all_buses

    @staticmethod
    def buses_on_route(route_id):
        return Bus._all_buses[route_id]

    @staticmethod
    def set_state(**kwargs):
        bus = Bus(**kwargs)
        Bus._all_buses[bus.route_id].append(bus)

    @staticmethod
    def load_state():
        """ Loads a fresh state of all buses from the web """
        Bus._all_buses = defaultdict(list)

    @property
    def route_id(self):
        return self._route_id

    @property
    def location(self):
        return self._location

    @property
    def stop(self):
        return BusStop.lookup(self._stop)

    @property
    def next_stop(self):
        return BusStop.lookup(self._next_stop)


class BusStop:

    _all_stops = dict()

    def __init__(self, stop_id):
        self._stop_id = stop_id

