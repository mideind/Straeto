
# Straeto

Straeto is a Python 3.x package encapsulating data about buses and bus
routes of Strætó bs, an Icelandic municipal bus service.

The data is fetched from the public [straeto.is website](https://straeto.is),
where it is stored in a file called `GTFS.zip`. Unfortunately, that file
is not (yet) located at a fixed, well-known URL.

## Installation

Straeto is a pure-Python package. It
is [available on PyPi](https://pypi.org/project/straeto/),
and can thus be installed by simply typing:

```shell
$ pip install straeto
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
for direction, times in schedule.arrivals(route_id, s.name, n=2).items():
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

This is a pre-alpha release and proper documentation has not yet been
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

## Copyright

*This program is copyright &copy; 2019 Miðeind ehf.*

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

This program and its authors are in no way affiliated with or endorsed by
Strætó bs.

---

*If you would like to use this software in ways that are incompatible*
*with the standard GNU GPLv3 license, please contact Miðeind ehf.*
*to negotiate alternative arrangements.*
