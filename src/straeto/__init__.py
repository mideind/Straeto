"""

    Straeto: A package encapsulating information about Iceland's buses and bus routes

    Copyright (C) 2023 Miðeind ehf.
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
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

    This module exposes the bus API, i.e. the identifiers that are
    directly accessible via the bus module object after importing it.

"""

# Expose the bus API
from .straeto import (
    Bus,
    BusSchedule,
    BusCalendar,
    BusRoute,
    BusService,
    BusTrip,
    BusStop,
    BusHalt,
    distance,
    locfmt,
    refresh,
    initialize,
)

# Debugging
from .straeto import (
    print_closest_stop,
    print_next_arrivals,
    _MIDEIND_LOCATION,  # type: ignore
)

__author__ = "Miðeind ehf."
__copyright__ = "(C) 2023 Miðeind ehf."
__version__ = "1.4.0"

__all__ = [
    "Bus",
    "BusSchedule",
    "BusCalendar",
    "BusRoute",
    "BusService",
    "BusTrip",
    "BusStop",
    "BusHalt",
    "distance",
    "locfmt",
    "refresh",
    "initialize",
    "print_closest_stop",
    "print_next_arrivals",
    "_MIDEIND_LOCATION",
]
