# RD Lažánky – nedořešené položky dokumentace

Stav kontroly: **25. 11. 2026**.

Interní pracovní seznam konkrétních zjištění z kontroly dokumentace. Není součástí vydávané projektové dokumentace ani úplným seznamem povinných příloh. Obecný seznam pro přípravu podání je v [checklist.md](checklist.md). „Nenalezeno v balíku“ neznamená, že podklad neexistuje u investora nebo projektanta.

## Chybějící nebo rozpracované části

- [ ] **D.1.1.1 – architektonicko-stavební technická zpráva.** V balíku jsou výkresy D.1.1.2, samostatná zpráva nebyla nalezena. Doplnit ji podle konečného stavebního řešení a koordinovat s B.
- [ ] **D.2.1 – stavebně konstrukční technická zpráva.** Doplnit popis nosného systému, materiálů, založení, stropů, krovu a jejich vazeb.
- [ ] **D.2.2 – základní statický výpočet.** Doplnit ucelený výpočet zahrnující základy a hlavní nosné konstrukce. Dosavadní pracovní výpočty krovu mimo vydávaný balík tuto část samy nepokrývají. Ověřit konečné rozměry základů a návaznost na únosnost podloží.
- [ ] **D.1.2.1-VZT – dokončení zprávy větrání.** [Pracovní návrh](<projekt2/D.1.2. Technologické řešení/VZT. Vzduchotechnika/D.1.2.1-VZT-01. Technická zpráva.md>) a PDF jsou připraveny. Normální provozní režim je potvrzen na 240 m³/h přívod i odvod, s přestupem 60 m³/h z přízemí do podkroví. Objemové kritérium 0,5 h⁻¹ při zakreslených průtocích ověřeno pro všechny čtyři obytné místnosti; viz kapitola 3.4. Potvrzen ručně spouštěný boost impulzním tlačítkem s časovým návratem a recirkulační digestoř. Doplnit umístění tlačítka, průtok a dobu boostu, snížený režim a funkční odvody; určit výkonové parametry jednotky, rozvody, přestupní otvory, sání a výfuk, kondenzát a hluk. Koordinovat kamna, recirkulační digestoř a samostatné větrání suterénu. Konkrétní výrobce zůstává otevřený.
- [ ] **D.1.2.1-VYT – dokončení zprávy vytápění a chlazení.** Pracovní návrh je v [topeni.md](topeni.md), dosud není vydanou zprávou v balíku `projekt2`. Doplnit zejména tepelné ztráty a chladicí zátěže, ověření výkonu TČ a fan-coilů, hydrauliku, regulaci, odvod kondenzátu a akustické posouzení venkovní jednotky. Uzavřít označené položky „DOPLNIT“ a zprávu zařadit do profesní části.

## Nesoulady ve zprávách a mezi profesemi

- [ ] **Aktualizovat B podle konečného modelu a výkresů.** Kontrola našla zejména:
  - jednotný údaj o šířce základových pasů **900 mm**, ačkoli model používá více různých šířek;
  - popis části zdiva jako **YTONG 30**, zatímco aktuální model používá **Porfix P2-440 PDK 300 mm**;
  - starší popis podlahových izolací; porovnat jej se současnými skladbami a odstraněním izolace ze stropu suterénu;
  - rozměry domu **9,15 × 9,40 m** a několik údajů o zastavěné ploše (**86 / 86,01 m²**); sjednotit se současným výpočtem a vyjasnit, ke kterému obrysu se plocha vztahuje. C nyní používá obrys **9,16 × 9,41 m**;
  - po sjednocení konstrukcí přepočítat také související objemy, plochy a uvedené světlé výšky.
- [ ] **Opravit staré odkazy a obsahy zpráv po přečíslování.** Například B stále odkazuje na „D1.1.10. Základy“ a „D1.1.4. Krov“; aktuálně jde o **D.2.3-01** a **D.2.3-06**. Přejmenování souborů nezměnilo obsah Word dokumentů. Zkontrolovat také titulní strany a vnitřní odkazy A, ELE a ZTI.
- [ ] **Vyčistit obsah zprávy ZTI.** V obsahu zůstaly kapitoly o vnitřním plynovodu, přestože se plynová přípojka nenavrhuje. Sjednotit obsah se skutečným rozsahem zprávy a aktualizovat pole obsahu.
- [ ] **Sjednotit popis likvidace dešťových vod v B a ZTI.** B uvádí přepad akumulační nádrže do dešťové kanalizace, ZTI uvádí vsakování. Výběr konečného řešení navazuje na samostatný návrh uvedený níže.
- [ ] **Sjednotit bilanci dešťových vod v B.** V textu je **73 m³/rok**, zatímco v tabulce **78,26 m³/rok**. Přepočítat podle konečných ploch a zvoleného řešení.
- [ ] **Koordinovat napájení TČ a hydroboxu s elektro.** Pracovní zpráva vytápění upozorňuje na jednofázovou variantu vybrané sestavy LG, zatímco dosavadní elektro návrh vycházel z třífázového přívodu. Potvrdit konkrétní zařízení a podle jeho návodů doplnit přívody, jištění a bilanci příkonů včetně dohřevu.
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
- [ ] Po převzetí **PENB** ověřit shodu jeho vstupů se skutečnými skladbami, otvory a technickými systémy.

## Již vyřešené body z této kontroly

- [x] Převod zpráv B a ZTI z DOCX do editovatelných Markdown souborů vedle originálů. Zachován text, tabulky a vložené obrázky; starý stránkovaný obsah byl odstraněn. Technické nesoulady uvedené výše zůstávají k opravě. Originální DOCX zůstaly beze změny.
- [x] Přeorganizování a přečíslování výkresů, včetně názvů souborů a razítek.
- [x] Doplnění C.1–C.2 a C.3 v dosud dohodnutém rozsahu; ČOV a dešťové hospodářství zůstávají odložené.
- [x] Doplnění odstupu uličního rohu od souseda a vzdálenosti k lesu; posunutí šipky „Zájmové území“ mimo dům.
- [x] Odstranění viditelných interních čísel bodů a odkazů na zdrojová data z výkresů. Poslední kontrola 34 PDF a textů/popisků zdrojových SVG nenašla tyto odkazy. Pracovní návrhy zpráv tím nebyly automaticky vyčištěny.

Po dokončení návrhů provést společnou kontrolu A–D: poloha a výšky domu, konstrukce a skladby, přípojky, bilance, číslování a odpovědní projektanti musí souhlasit. Doplnit požadované autorizace a připravit konečnou vydávanou sadu.
