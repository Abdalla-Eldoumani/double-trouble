# Facts

Every claim about the world that the engine, app, README or pitch relies on. One entry per claim: the claim, the source, the date it was checked, and the supporting line quoted short. Anything not supported by a primary source is listed under Unverified and must not be stated as fact.

## Verified

### 1. The Government of Alberta maintains Deerfoot Trail inside Calgary

- Source: Government of Alberta, Highway maintenance. https://www.alberta.ca/highway-maintenance (page dated 2026-08-05)
- Checked: 2026-10-03
- Supporting lines:
  - "The Government of Alberta (GoA) is responsible for maintaining highways to a safe standard."
  - "Contractors provide highway maintenance operations in 25 contract maintenance areas (CMAs) of the province, the Deerfoot Trail in Calgary, and the ring roads around Calgary and Edmonton."
  - Contractor table row: "Deerfoot Trail | Deerfoot Trail, City of Calgary"

### 2. The Government of Alberta maintains the Calgary ring road

- Source: same page as entry 1. https://www.alberta.ca/highway-maintenance
- Checked: 2026-10-03
- Supporting line: "... the Deerfoot Trail in Calgary, and the ring roads around Calgary and Edmonton."

### 3. Stoney Trail is the Calgary ring road and part of the provincial highway network

- Source: Government of Alberta, Ministry of Transportation, "Calgary ring road now offers 70 km of free-flow traffic" (2013). https://www.transportation.alberta.ca/5463.htm
- Checked: 2026-10-03
- Supporting lines:
  - "Albertans can now take the Calgary Ring Road from Macleod Trail on the city’s south side, along the eastern border and around the north connecting with Highway 1 toward Banff."
  - "A vital part of the provincial highway network ..., Stoney Trail supports Alberta’s vision ..."
- Also: Government of Alberta, Stoney Trail Functional Planning Study (2007). https://www.transportation.alberta.ca/stfps.htm. "Stoney Trail, which forms the NW part of the Ring Road, extends from Highway 1 (Trans-Canada Highway) to Highway 2 (Deerfoot Trail)."
- Note: both pages are old. Entry 2 is the current source for who maintains the ring road; this entry only ties the name Stoney Trail to the ring road.

### 4. The City of Calgary runs traffic safety programs and spot safety improvements on City roads, under its Mobility business unit

- Source: The City of Calgary, Traffic safety programs. https://www.calgary.ca/roads/safety.html
- Checked: 2026-10-03
- Supporting lines:
  - "The Calgary safer mobility plan is a five-year plan aimed at improving the safety of our transportation network."
  - "... spot improvements for traffic safety contact 311 or fill out the online form."
  - "Current innovative traffic safety pilot projects lead by the Traffic Safety team ..."
  - Page metadata (not visible text): org = "City of Calgary Administration/Operational Services/Mobility"
- Use "The City of Calgary Mobility business unit (Traffic Safety team)" when naming the customer. See Unverified for "City of Calgary Roads".

### 5. The Traffic Incidents dataset is published by The City of Calgary on Open Calgary

- Source: Open Calgary, Traffic Incidents. https://data.calgary.ca/Transportation-Transit/Traffic-Incidents/35ra-9556
- Checked: 2026-10-03
- Supporting lines: "Data Provided By The City of Calgary", "Dataset Owner Calgary Open Data", "License: See Terms of Use", "Business Unit | Mobility"
- What the feed is, in the City's words (about_data tab, https://data.calgary.ca/Transportation-Transit/Traffic-Incidents/35ra-9556/about_data):
  - "This is an unofficial archive of traffic incidents within Calgary."
  - "Traffic incidents are traffic disruptions affecting traffic flow, such as traffic signal issues, hazardous road conditions, stalled vehicles, and unverified, unreported traffic collisions."
  - "This data is based off unrecorded imagery where traffic cameras are present. There may be gaps in the data due to system or script malfunction."
- Consequence: results are incidents seen on traffic cameras, not confirmed collisions, and places without cameras are likely under-counted. Say so wherever results are shown.

### 6. Open Calgary data is licensed under the Open Government Licence - City of Calgary, version 2.1, which requires an attribution statement

- Source: Open Calgary Terms of Use. https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa/
- Checked: 2026-10-03
- Supporting lines:
  - "This is version 2.1 of the Open Government Licence – City of Calgary."
  - "Acknowledge the source of the Information by including any attribution statement specified by the Information Provider(s) and, where possible, provide a link to this license."
  - Attribution statement: "Contains information licensed under the Open Government Licence – City of Calgary."
  - Non-endorsement: "This licence does not grant you any right to use the Information in a way that suggests any official status or that the Information Provider endorses you or your use of the Information."
- Consequence: the attribution line is in the engine's `dataset.source`. The app and README should show it with a link to the licence, and nothing may suggest the City endorses this project.

### 7. pandas 3.0 parses date strings to microsecond resolution and infers a dedicated `str` dtype for text

- Source: pandas 3.0.0 release notes. https://pandas.pydata.org/docs/whatsnew/v3.0.0.html
- Checked: 2026-10-03. pandas.pydata.org is blocked from the build environment, so the page was read through a documentation mirror of the same URL. The installed pandas 3.0.6 matched it: `start_dt` loads as `datetime64[us]` and text columns as `str`.
- Supporting lines:
  - "The new default resolution when parsing strings is microseconds, falling back to nanoseconds when the precision of the string requires it."
  - "Starting with pandas 3.0, a dedicated string data type is enabled by default"
- Consequence for the engine: it compares timestamps but never casts them to integers, so the resolution change does not affect results.

## Unverified

- **"City of Calgary Roads" as the name of the unit that funds or builds safety improvements.** The traffic safety page sits under calgary.ca/roads, but its metadata names the Mobility business unit. Use "The City of Calgary (Mobility)" unless a City source names a Roads unit.
- **Any planned handover of Deerfoot Trail from the Province to the City.** Seen only in secondary sources (news headlines, an encyclopedia summary). Not stated anywhere in this project.
- **That every crash at an intersection named for Deerfoot or Stoney happened on provincial road.** The provincial flag matches by name, so it also catches the City-road leg of each interchange (for example 16 Avenue NE at Deerfoot Trail). The sources above support "Deerfoot Trail and Stoney Trail are provincially maintained", not "every incident at these interchanges is on provincial road".
