# RD Lažánky – nedořešené položky dokumentace

Stav kontroly: **26. 11. 2026**.

Interní pracovní seznam konkrétních zjištění z kontroly dokumentace. Není součástí vydávané projektové dokumentace ani úplným seznamem povinných příloh. Obecný seznam pro přípravu podání je v [checklist.md](checklist.md). „Nenalezeno v balíku“ neznamená, že podklad neexistuje u investora nebo projektanta.

## Chybějící nebo rozpracované části

- [ ] **D.1.1.1 – architektonicko-stavební technická zpráva.** V balíku jsou výkresy D.1.1.2, samostatná zpráva nebyla nalezena. Doplnit ji podle konečného stavebního řešení a koordinovat s B.
- [ ] **D.2.1 – stavebně konstrukční technická zpráva.** Doplnit popis nosného systému, materiálů, založení, stropů, krovu a jejich vazeb.
- [ ] **D.2.2 – základní statický výpočet.** Doplnit ucelený výpočet zahrnující základy a hlavní nosné konstrukce. Dosavadní pracovní výpočty krovu mimo vydávaný balík tuto část samy nepokrývají. Ověřit konečné rozměry základů a návaznost na únosnost podloží.
- [ ] **D.1.2.1-VZT – ověření a koordinace návrhu větrání.** [Technická zpráva](<projekt2/D.1.2. Technologické řešení/VZT. Vzduchotechnika/D.1.2.1-VZT-01. Technická zpráva.md>) a PDF specifikují **Östberg HERU 100 T EC-y2 s Pressure Control IQC**, umístěnou v nevytápěném 1.PP v S.04 na stěně k S.05. Obsazenost 4 osoby, normální režim 240/240 m³/h, ruční boost 300/300 m³/h na 20 minut; objemové kritérium 0,5 h⁻¹ ověřeno. Hliníkový rotor a ocelové vnitřní panely; menší polymerní části včetně oběžných kol jsou uvedeny ve zprávě. Parametry ErP 84,8 % a PHI 77 % / 0,38 Wh/m³ se používají se zohledněním odlišných zkušebních podmínek; boost je mimo certifikovaný rozsah PHI. Elektro: 230 V, katalogově 1,41 kW včetně dohřevu 1,2 kW. Hlavní DN 200 přes přechody z Ø 125, koncové větve 1× Ø 90 pro 40 m³/h a 2× Ø 90 pro 60 m³/h, izolace min. 50 mm. Standardní kondenzátní odvod jednotky se nenavrhuje. Potvrzeny recirkulační digestoř, zahradní sání i výfuk přes suterén; suterén a garáž bez vyústek. Doplnit trasy a zakončení, ověřit tlakové ztráty při rezervě 150 Pa na každé cestě, kondenzaci a přenos hluku ze suterénu včetně tlumičů pro příspěvek celé VZT nejvýše 25 dB(A) v pokojích 0.01–0.03. Ověřit servisní přístup a levé/pravé provedení; zkoordinovat napájení jednotky v S.04 a ovládací vedení k tlačítku v 0.04, přestupní prvky, kamna, PBŘ a PENB. Venkovní návrhové teploty −15 °C a +32 °C.
- [ ] **D.1.2.1-VYT – dokončení zprávy vytápění a chlazení.** Pracovní návrh je v [topeni.md](topeni.md), dosud není vydanou zprávou v balíku `projekt2`. Doplnit zejména tepelné ztráty a chladicí zátěže, ověření výkonu TČ a fan-coilů, hydrauliku, regulaci, odvod kondenzátu a akustické posouzení venkovní jednotky. Uzavřít označené položky „DOPLNIT“ a zprávu zařadit do profesní části.

## Nesoulady ve zprávách a mezi profesemi

- [ ] **Přepočítat obestavěný prostor v B.** Původních 911,60 m³ není doloženo výpočtem současné geometrie; v B je údaj označen k přepočtu. Konstrukční popis, zastavěná plocha hlavního objemu 86,20 m², úrovně a součet čistých ploch místností 184,47 m² jsou aktualizovány. Při konečné bilanci zachovat výslovné rozlišení čistých ploch místností od jinak definovaných podlahových či energetických ploch.
- [ ] **Sjednotit materiálové názvy a legendy stavebních výkresů.** Rozpor 250/240 mm v B je opraven: obvodové VPC obou obytných podlaží má 240 mm. V půdorysných legendách ještě ověřit správné označení pevnosti a objemové hmotnosti VPC, rozlišení Porfixu 300 mm od Ytongu Klasik 300 mm a shodu se zvolenými výrobky.
- [ ] **Opravit staré odkazy a obsahy ostatních zpráv po přečíslování.** Výkresové odkazy v konstrukčním popisu B jsou aktualizovány na D.1.1.2 a D.2.3. Zkontrolovat také titulní strany a vnitřní odkazy A, ELE a ZTI; původní DOCX nebyly automaticky přepsány.
- [ ] **Vyčistit obsah zprávy ZTI.** V obsahu zůstaly kapitoly o vnitřním plynovodu, přestože se plynová přípojka nenavrhuje. Sjednotit obsah se skutečným rozsahem zprávy a aktualizovat pole obsahu.
- [ ] **Sjednotit popis likvidace dešťových vod v B a ZTI.** B uvádí přepad akumulační nádrže do dešťové kanalizace, ZTI uvádí vsakování. Výběr konečného řešení navazuje na samostatný návrh uvedený níže.
- [ ] **Sjednotit bilanci dešťových vod v B.** V textu je **73 m³/rok**, zatímco v tabulce **78,26 m³/rok**. Přepočítat podle konečných ploch a zvoleného řešení.
- [ ] **Koordinovat napájení TČ a hydroboxu s elektro.** Pracovní zpráva vytápění upozorňuje na jednofázovou variantu vybrané sestavy LG, zatímco dosavadní elektro návrh vycházel z třífázového přívodu. Sestava LG HU051MR.U44 + HN091MR.NK5 je potvrzena; podle jejích návodů doplnit přívody, jištění a bilanci příkonů včetně dohřevu.
- [ ] **Dokončit schéma rozvaděče.** Parametry přívodní části byly na přání investora ponechány otevřené. Doplnit je při návrhu elektro a ověřit shodu obvodů se všemi půdorysy a technickou zprávou.
- [ ] **Odstranit pracovní odkazy před vydáním zprávy vytápění.** `topeni.md` zatím obsahuje interní názvy modelu, adresářů a referenční zprávy jiného domu. Ve vydané verzi používat názvy a čísla projektových částí a relevantní výrobní podklady.

## Záměrně odložený návrh

- [ ] **ČOV a venkovní splašková kanalizace.** Samostatně navrhnout umístění, potrubí a konečný způsob nakládání s vyčištěnou vodou. B zatím zmiňuje AS Variocomp 5k pro 5 EO; tento údaj nepovažovat za dokončený návrh. Po rozhodnutí doplnit C.3, ZTI a B.
- [ ] **Akumulace dešťové vody a navazující odvodnění.** Samostatně dořešit uvažovanou nádrž **10 m³**, umístění, potrubí, bilanci a přepad/vsakování. Poté sjednotit C.3, ZTI a B. Investor výslovně odložil tento návrh na další krok.

## Podklady k doložení a ověření

- [ ] **Radonový průzkum.** B uvádí provedené měření a střední radonový index, samotný protokol nebyl v kontrolovaném balíku nalezen. Dohledat jej a ověřit návaznost návrhu ochrany; nejde automaticky o požadavek na nové měření.
- [ ] **Podklady pro založení.** Ověřit dostupnost a dostatečnost geotechnických podkladů pro konečný statický návrh. Jejich existenci ani obsah dosavadní kontrola nepotvrdila.
- [ ] **Blízkost lesa.** C.3 nově ukazuje vzdálenost k hranici lesního pozemku **806/16 přibližně 11,70 m**. Prověřit návaznost na text B a potřebné podklady či stanoviska; doplněná kóta sama toto ověření nenahrazuje.
- [ ] **Před podáním ověřit účinné předpisy a požadovanou formu dokumentace pro skutečné datum podání.** Obecný checklist má starší datum kontroly; jeho právní odkazy a formuláře znovu prověřit.

## Externě zajišťované části

**PBŘ a PENB nejsou vedeny jako chybějící návrh pro tuto práci:** investor je zadal jiným zpracovatelům.

- [ ] Po převzetí **PBŘ** zapracovat požárně bezpečnostní údaje do navazujících částí, zejména C.3, a ověřit shodu s dispozicemi a konstrukcemi.
- [ ] **Kamna a komín – koordinace pro PBŘ a provedení.** Investor zvolil **HAAS+SOHN PISA RLU na kusové dřevo**, v poloze podle půdorysu 2.NP s možností drobného posunu, a **Schiedel ABSOLUT**. [Technický list kamen](https://www.nejenkrby.cz/materialy/0429112710000_TD.pdf): Pnom 5,0 kW, kouřovod Ø 150 mm, minimální tah 12 Pa, rozměry 460 × 488 × 1441 mm; odstupy od hořlavých materiálů vzadu / boky / vpředu / ke stropu 200 / 300 / 800 / 800 mm. Ověřit osazení včetně podlahové ochrany, kouřovodu, nábytku a sloupků; půdorysná značka kamen je dosud schematická. Dimenzovat spalinovou cestu a těsný přívod spalovacího vzduchu, zkoordinovat souběh s VZT a přístup k čištění. **Model 500 × 400 mm s průduchem Ø 200 mm není ověřenou výrobkovou geometrií:** [Schiedel – technický list ABSOLUT](https://www.schiedel.com/downloads/cs-CZ/Projek%C4%8Dn%C3%AD%20podklady/2023-05-technicky-list-absolut-2019%20.pdf) uvádí pro provedení se šachtou ABS 20L vnější rozměr 540 × 380 mm a pro ABS 12L–18L rozměr 500 × 360 mm (při orientaci delší stranou podél X). Po volbě průměru a způsobu přívodu vzduchu upravit těleso, základ, prostupy a odstupy v modelu společně. [Montážní návod ABSOLUT, 09/2026](https://www.schiedel.com/downloads/cs-CZ/Mont%C3%A1%C5%BEn%C3%AD%20n%C3%A1vody/montazni-navod-absolut-tisk-a3-2026.pdf) požaduje min. 30 mm k nehořlavým konstrukcím a 50 mm ke dřevu; dosavadní 30mm mezera v MIAKO není požárním odstupem pro dřevěné části střechy.
- [ ] Po převzetí **PENB** ověřit shodu jeho vstupů se skutečnými skladbami, otvory a technickými systémy.
- [ ] **Dopracovat vstupy pro PENB.** Okna Uw ≤ 1,20 W/(m²·K); doplnit g, podíl rámu a parametry dveří. Vodivosti izolací λD jsou uvedeny ve skladbách SK1–SK7, B a vrstvy.md; použít návrhové korekce a správné vlastnosti zdiva. LG HU051MR.U44 + HN091MR.NK5 je potvrzeno, návrh 45/40 °C ekvitermně a 7/12 °C při chlazení. Doplnit výkonové a účinnostní vstupy, použití elektrodohřevu a výsledky výpočtů zátěží. Vybrat 400l zásobník TV s vhodným výměníkem a doložit jeho tepelnou ztrátu; prozatím uvažováno 55 °C a varianta bez cirkulace, ověřit čekací dobu. Potvrdit energetické vstupy HERU v pracovním bodě, stínění, tepelné mosty a systémovou hranici k nevytápěnému suterénu. Převzít aktuální geometrii z modelu; rozměry a plochy B/C.3 po posledních změnách domu znovu sjednotit.

## Již vyřešené body z této kontroly

- [x] Aktualizace konstrukčního popisu B podle současného návrhu: základové pasy a odskok, zdivo včetně Porfixu a Ytongu podle polohy, věnce, MIAKO a HEB, dřevěné schodiště a podpory, skladby SK1–SK7, uzavření rezervy pro schody do suterénu, fasáda, komín, světlé výšky a výškové osazení. Opraveny související zastavěné a čisté půdorysné plochy; obestavěný prostor zůstává k samostatnému přepočtu.

- [x] Převod zpráv B a ZTI z DOCX do editovatelných Markdown souborů vedle originálů. Zachován text, tabulky a vložené obrázky; starý stránkovaný obsah byl odstraněn. Technické nesoulady uvedené výše zůstávají k opravě. Originální DOCX zůstaly beze změny.
- [x] Přeorganizování a přečíslování výkresů, včetně názvů souborů a razítek.
- [x] Doplnění C.1–C.2 a C.3 v dosud dohodnutém rozsahu; ČOV a dešťové hospodářství zůstávají odložené.
- [x] Doplnění odstupu uličního rohu od souseda a vzdálenosti k lesu; posunutí šipky „Zájmové území“ mimo dům.
- [x] Odstranění viditelných interních čísel bodů a odkazů na zdrojová data z výkresů. Poslední kontrola 34 PDF a textů/popisků zdrojových SVG nenašla tyto odkazy. Pracovní návrhy zpráv tím nebyly automaticky vyčištěny.

Po dokončení návrhů provést společnou kontrolu A–D: poloha a výšky domu, konstrukce a skladby, přípojky, bilance, číslování a odpovědní projektanti musí souhlasit. Doplnit požadované autorizace a připravit konečnou vydávanou sadu.
