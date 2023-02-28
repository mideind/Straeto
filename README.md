[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.7](https://img.shields.io/badge/python-3.7-blue.svg)](https://www.python.org/downloads/release/python-370/)
[![Release](https://shields.io/github/v/release/mideind/Straeto?display_name=tag)]()
[![Build](https://github.com/mideind/Straeto/actions/workflows/python-package.yml/badge.svg)]()

# Straeto

**Straeto** is a Python 3 (>= 3.7) package encapsulating data about buses and bus
routes of Strætó bs, an Icelandic municipal bus service.

The data is fetched from an open data file released by
Strætó bs called [`GTFS.zip`](http://opendata.straeto.is/data/gtfs/gtfs.zip).
This file is large and doesn't change often. Please do not
fetch it frequently or frivolously. An interval of at least 24 hours
should be more than enough.

Note that the process that fetches the `GTFS.zip` file must have
file create and file write rights on the `resources/` subdirectory
within the Straeto source package.

## Installation

Straeto is a pure-Python package. It
is [available on PyPi](https://pypi.org/project/straeto/),
and can thus be installed by simply typing:

```shell
pip install straeto
```

## Usage

Example:

```python
import straeto
# Your location here, as a (lat, lon) tuple
location = straeto._MIDEIND_LOCATION  # Fiskislóð 31, Reykjavík
s = straeto.BusStop.closest_to(location)
print("The bus stop closest to {0} is {1}".format(location, s.name))
# Load the bus schedule for today
schedule = straeto.BusSchedule()
# Your route identifier here
route_id = "14"
# Print the next two arrivals of that route at the closest bus stop
arrivals, arrives = schedule.arrivals(route_id, s, n=2)
if not arrives:
    # This stop is not in the schedule for this route
    print("The bus does not stop at {0}".format(s.name))
else:
    for direction, times in arrivals.items():
        print(
            "Direction {0}: {1}"
            .format(
                direction,
                ", ".join(
                    "{0:02}:{1:02}".format(hms[0], hms[1]) for hms in times
                )
            )
        )
```

## Documentation

This is a beta release and proper documentation has not yet been
produced. But the code is fairly self-explanatory; look at the file
`src/straeto/straeto.py` to see the source code for the main classes
and some usage examples.

## Real-time Data

Optionally, and in addition to static schedule data, this package supports
reading real-time data about bus locations from a URL
provided by Strætó bs.  However, these URLs are not public and you need to sign
an agreement with Strætó to get access to the data and obtain your own URL. Once you
have your URL, put it in the file `config/status_url.txt` to enable the Straeto
package to fetch real-time data.

## Release history

* Release **1.4.0**

    Full type annotations. Python requirement bumped to 3.7.

* Release **1.3.0**

    Added type annotations; fixed Python 3.6 compatibility
    regression.

* Release **1.2.0**

    Updated and hardened the code that reads Strætó.bs' XML configuration file.
    Added type annotations.

* Release **1.1.0**

    Added type annotations; modified the `BusStop.closest_to()` function;
    updated the default resources files that accompany the
    Straeto package.

* Release **1.0.2**

    Updated the default resources files that accompany the
    Straeto package.

* Release **1.0.1**

    Updated the code to reflect a change in the format of the
    `stop_times.txt` file, going from 6 fields to 7.

* Release **1.0.0**

    Beta release. Supports downloading and extraction of the `GTFS.zip`
    schedule file from the Strætó bs open data URL. Fixes a bug where sequential
    bus halts with identical time points were not being included in the schedule.

* Release **0.0.10**

    Better support for Windows with explicit specification of UTF-8 encoding
    for files

## Copyright

*This program is copyright &copy; 2023 Miðeind ehf.*

## License

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

The full text of the GNU General Public License is available at
[http://www.gnu.org/licenses/](http://www.gnu.org/licenses/).

## No Affiliation

This program and its authors are in no way affiliated with
or endorsed by Strætó bs.

---

*If you would like to use this software in ways that are incompatible*
*with the standard GNU GPLv3 license, please contact Miðeind ehf.*
*at [mideind@mideind.is](mailto:mideind@mideind.is)*
*to negotiate alternative arrangements.*
