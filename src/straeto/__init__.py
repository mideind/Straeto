"""

    Straeto: A package encapsulating information about buses and bus routes

    Copyright (C) 2020 Miðeind ehf.
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
    _MIDEIND_LOCATION,
)

__author__ = "Miðeind ehf."
__copyright__ = "(C) 2020 Miðeind ehf."
# Remember to update the version in setup.py as well
__version__ = "1.0.2"
