# Map outlines

`countries.json` is Natural Earth's 1:50m Admin 0 countries
(naturalearthdata.com, public domain), cut down for engines/maps.py: the
ADM0_A3 and ISO codes, the English, Turkish, Polish and German names, and
each polygon's outer ring with coordinates rounded to 0.01° (about a
kilometre — far finer than a phone screen shows a country). Holes are
dropped. Source: `ne_50m_admin_0_countries.geojson` from
github.com/nvkelso/natural-earth-vector.
