# Draft: ESA / Copernicus — Sentinel-2 licence clarification

**Status:** draft, not sent. Fill the bracketed fields and send.
**To:** the Copernicus Data Space Ecosystem service desk —
`help-cdse@esa.int`, or the support form at
<https://helpcenter.dataspace.copernicus.eu/>.
**Subject:** Sentinel-2 licence terms for a commercial derived product — CC BY-SA or the Copernicus regulation?

---

Hello,

I am building a commercial web application that derives statistics from
Sentinel-2 imagery over England. Users draw a site boundary and receive a
monthly time series of vegetation and moisture indices — NDVI, NDMI, NDBI and
similar — computed as spatial means over that boundary. Users receive
**aggregated numbers, not imagery**: no Sentinel pixels, tiles or scenes are
redistributed.

I have two questions about the licence that governs this.

**1. Which licence actually applies?** I have seen Sentinel-2 data described
both as being subject to the Copernicus data policy — Regulation (EU)
No 377/2014 and the Legal Notice on the use of Copernicus Sentinel Data and
Service Information, which as I read it permits free use including commercial
reuse and the creation of derived works — and, in some catalogue metadata, as
**CC BY-SA 3.0 IGO**. Those are materially different for us. Share-alike, if
it applies and if it reaches our derived statistics, would require us to
license our own product's outputs under compatible terms, which we would need
to design around rather than discover later.

Could you confirm which applies to Sentinel-2 Level-2A surface reflectance
obtained through the Copernicus Data Space Ecosystem?

**2. Where does "derived work" end?** Assuming the Copernicus terms apply,
does a spatial mean of a band-ratio index over a user's polygon — a single
number per month, with no imagery redistributed — count as a derived work
subject to the same terms, or as information derived from the data and outside
them? I ask specifically because we intend to let customers export those
numbers as CSV.

We already carry the attribution the Legal Notice requires: every dataset in
our catalogue displays its notice — "Contains modified Copernicus Sentinel
data [year]" for Sentinel-2 — in the interface and in every export, alongside
the source, resolution and licence. If the correct wording for a
statistics-only derived product differs from that, please tell me and I will
change it.

Thank you,

[NAME]
[COMPANY]
[EMAIL]

---

## Notes for whoever sends this

- **This email is the cheaper of the two questions and should go first.** If
  the answer is "Copernicus terms, commercial reuse permitted, attribution
  only", then Sentinel-2 direct from the Copernicus Data Space is a complete
  route around the Earth Engine licence for the eleven Sentinel-2 indices —
  which is 11 of the 24 Earth Engine factors, and the most-used ones.
- The other three Earth Engine sources are already clear and do not need an
  email: ERA5-Land is Copernicus C3S with attribution, MODIS LST is US
  government public domain, ESA WorldCover is CC BY 4.0. All three are marked
  `commercial: "yes"` in `catalog.py`. Only Sentinel-2 and Sentinel-1 are
  marked `"verify"`, and they share a licence entry, so one answer settles
  both.
- **When the answer arrives, fix `catalog.py`.** The `licence` and
  `commercial` fields for `sentinel2_sr` and `sentinel1_sar` are what the
  application shows users under Sources; today they say CC BY-SA 3.0 IGO and
  `"verify"`. One of those two readings is wrong and the app is currently
  displaying a licence it has not confirmed.
- Record the reply and its date in `DECISION-LOG.md` in this folder.
