# D.1.2.1-VYT-01. Vytápění a chlazení

## Technická zpráva – pracovní návrh

| Identifikační údaj | Hodnota |
|---|---|
| Stavba | RD Lažánky |
| Investor | Ing. Jiří Bobek |
| Autor návrhu | Ing. Jiří Bobek |
| Stupeň dokumentace | DSP – pracovní návrh profesní části |
| Datum | 27. 11. 2026 |
| Hl. ing. projektu | Ing. Josef Chovan |
| Zod. projektant | Ing. Josef Chovan |
| Katastrální území | Lažánky u Blanska, 679453 |
| Pozemky řešené stavební dokumentací | 105, 106/1, 103/2 |

Zpráva zachycuje potvrzený záměr investora a předběžné technické řešení. Označení **DOPLNIT** vymezuje údaje vyžadující výpočet nebo výběr konkrétního příslušenství. Zjednodušenou zimní bilanci obsahuje příloha D.1.2.1-VYT-02; navazující technickou kontrolu, vyšší odběr TV a variantu 40/35 °C obsahuje příloha D.1.2.1-VYT-03. Kapitola 12 rozlišuje původní odhad a kontrolu s návrhovými korekcemi vodivostí. Neuzavřené zůstávají zejména předání tepla do chodeb/WC, tichý výkon FCU, přesné nabíjení zásobníku a letní zátěže.

## 1. Úvod

Předmětem části D.1.2 – vytápění a chlazení je vytápění a letní chlazení rodinného domu tepelným čerpadlem vzduch–voda a pěti vodními ventilokonvektory. Součástí řešení je příprava teplé vody pro čtyři osoby v samostatném zásobníku o objemu 400 l.

Suterén nebude vytápěn. V obytných podlažích budou jedinými koncovými zařízeními ústřední otopné a chladicí soustavy fan-coily; podlahové vytápění ani další otopná tělesa nejsou součástí záměru. Kamna v obývacím pokoji budou sloužit k doplňkovému vytápění a nebudou hydraulicky propojena s tepelným čerpadlem.

## 2. Vstupní parametry a podklady

### 2.1. Popis objektu

Rodinný dům má suterén, přízemí a obytné podkroví. V přízemí jsou tři pokoje, koupelna a chodba se schodištěm. V podkroví se nachází obývací pokoj s kuchyňským koutem, chodba s umyvadlem a pračkou a samostatné WC. Suterén obsahuje skladovací a garážové prostory.

Pro tepelnětechnický výpočet se použijí aktuální skladby konstrukcí, rozměry, výplně otvorů a vazby k nevytápěnému suterénu ze stavební části. Větrání s rekuperací tepla řeší samostatná část D.1.2 VZT; její návrhové průtoky a účinnost se zohlední při výpočtu tepelných ztrát. Fan-coily zajišťují úpravu teploty vnitřního vzduchu, přívod čerstvého vzduchu zajišťuje větrací soustava.

### 2.2. Návrhové podmínky

| Veličina | Zadání pro tento návrh |
|---|---|
| Lokalita | Lažánky; přesné určení staveniště podle stavební části |
| Výpočtová venkovní teplota pro vytápění | −15 °C, shodně s částí VZT |
| Vnitřní teplota při vytápění | 20 °C podle požadavku investora, včetně koupelny |
| Vnitřní teplota při chlazení | 25 °C podle požadavku investora |
| Letní venkovní podmínky a návrhová vlhkost | +32 °C, shodně s částí VZT; vlhkost doplnit pro výpočet chladicí zátěže |
| Suterén | Bez aktivního vytápění a chlazení; pro zjednodušenou konzervativní kontrolu −15 °C, citlivost při 0 až +10 °C; skutečná teplota není stanovena |
| Počet uživatelů pro přípravu TV | 4 osoby |

### 2.3. Podklady

- Aktuální stavební půdorysy, řezy a skladby konstrukcí části D.1.1 a konstrukční podklady části D.2.
- Koordinační podklady částí D.1.2 ELE – elektroinstalace, D.1.2 ZTI – zdravotně technické instalace a D.1.2 VZT – řízené větrání.
- Zadání investora: sestava LG, pět fan-coilů IVAR, vytápění i chlazení, zásobník TV 400 l, nevytápěný suterén a doplňková kamna.
- Výrobní podklady uvedené u příslušných zařízení níže.

Výstupy této profesní části tvoří tato technická zpráva a související výkresy:

- **D.1.2.1-VYT-02 – Zjednodušený výpočet tepelné ztráty.**
- **D.1.2.1-VYT-03 – Technické ověření vytápění a přípravy TV.**
- **D.1.2.2-VYT-01 – Vytápění a chlazení, půdorys 1.NP.**
- **D.1.2.2-VYT-02 – Vytápění a chlazení, půdorys 2.NP.**

Pro dopracování jsou základními normovými podklady [ČSN EN 12831-1 – výpočet tepelného výkonu pro vytápění](https://csnonline.agentura-cas.cz/Detailnormy.aspx?k=505721) a [ČSN EN 12828+A1 – navrhování teplovodních otopných soustav](https://csnonline.agentura-cas.cz/Detailnormy.aspx?k=96137). Navazující požadavky, použitelné změny a rozsah dalších norem se upřesní podle konečného provedení zařízení.

## 3. Základní koncepční řešení

Venkovní jednotka tepelného čerpadla bude umístěna na uliční straně domu v návaznosti na suterénní průčelí. Vnitřní hydraulický modul a samostatný zásobník TV budou v koupelně 0.05 v přízemí. Jejich umístění vychází z výkresové části; osazovací a servisní prostory budou koordinovány s konkrétními výrobky.

Za hydraulickým modulem bude uzavřená dvoutrubková soustava s nuceným oběhem. Pět fan-coilů bude připojeno paralelně přes pětiokruhový rozdělovač se sběračem, vhodný pro topnou i chladicí vodu. Předběžný hydraulický návrh v kapitole 4.2 počítá s vestavěným čerpadlem, sériovou objemovou nádobou a diferenčním obtokem.

Soustava bude mít společný režim vytápění nebo chlazení. Jednotlivé místnosti budou regulovány samostatně, avšak dvoutrubkové zapojení neumožní současné vytápění jedné místnosti a chlazení jiné. Při požadavku na ohřev TV bude tepelné čerpadlo přepnuto do režimu nabíjení zásobníku; konkrétní priority a časová omezení se nastaví při uvedení do provozu.

Chodby 0.04 a 1.03 a WC 1.02 nemají v současném rozmístění vlastní otopné těleso. Kontrola VYT-03 dává při 20 °C přibližně **600 W / 275 W / 19 W** jejich vlastních ztrát. Vzduch přestupující ze stejně teplých místností tyto ztráty nepokrývá. Při snížení teploty obou chodeb na 18 °C předá předepsaných 160 m³/h přestupujícího vzduchu jen asi 109 W, zatímco jejich ztráta zůstává přibližně 825 W v konzervativním případě. Bez doložení dalšího přenosu nelze tvrdit, že ani 18 °C bude dosaženo. **Koncepce pěti FCU při požadavku 20 °C ve všech těchto prostorech není uzavřena:** je nutné rozhodnout o konkrétním předání tepla nebo rozdělení koncových zařízení. Touto kontrolou se počet ani poloha FCU nemění.

## 4. Zdroj tepla a chladu

### 4.1. Potvrzené tepelné čerpadlo

Investorem je potvrzena sestava **LG THERMA V, venkovní jednotka HU051MR.U44 a vnitřní hydrobox HN091MR.NK5**. Jde o splitovou sestavu s chladivem R32 a chladivovým propojením mezi jednotkami. Výrobce uvádí jmenovitý topný výkon **5,50 kW při A7/W35**. Tato hodnota charakterizuje katalogový provozní bod, nikoli ověřený výkon při návrhové zimní teplotě konkrétní stavby. [Podklad LG – R32 Split Hydro Box, specifikace sestavy](https://www.lg.com/gr/business/download/airsolution/Therma_V_R32_Split_Leaflet%5B20220621_225825898%5D.pdf)

Výrobní tabulka uvádí pro tuto sestavu maximální výkon **4,99 kW při A−15/W40** a **4,85 kW při A−15/W45**, včetně vlivu odmrazování. Kontrola VYT-03 s návrhovými korekcemi λ dává ztrátu **4,80 kW** při suterénu −15 °C a **4,40 kW** při suterénu +5 °C. Při W40 tedy zbývá v konzervativním případě jen asi 0,19 kW. Nejde o automatickou rezervu pro ohřev TV nebo zátop ani o výkon v tichém režimu. Ponechává se automatický elektrický dohřev, v zimní bilanci se nepředpokládá obsluha kamen. Minimální modulace a počet startů nejsou z těchto maximálních výkonů určitelné. [LG – tabulka maximálních výkonů R32 Split, strana 2](https://www.lg.com/content/dam/channel/wcms/hu/business/download/airsolution/2021_THERMA_V_%28AWHP%29_R32_Split_R410A_Split_leaflet_0302_FIN_20211102_223018918_.pdf).

Hydrobox obsahuje hydraulické a zabezpečovací prvky; pro tuto variantu katalog uvádí elektrický dohřev 6 kW ve dvou stupních, expanzní nádobu 8 l a pojistný ventil 3 bar. Předběžná kontrola expanze a prostorového bodu bivalence je v příloze VYT-03; neznamená zákaz dohřevu nad tímto bodem. Souběhy, režim TV a definitivní nastavení se ověří podle skutečného zapojení. [Technické údaje LG](https://www.lg.com/gr/business/download/airsolution/Therma_V_R32_Split_Leaflet%5B20220621_225825898%5D.pdf)

### 4.2. Hydraulické uspořádání

#### 4.2.1. Průtok a dostupný objem vody

Pro sestavu 5 kW uvádí LG jmenovitý průtok **15,8 l/min = 0,948 m³/h**, doporučené minimum **15 l/min** a disponibilní dopravní výšku **7,3 m vodního sloupce** při jmenovitém průtoku. Hodnota 7 l/min, uváděná pro vybavení průtokovým snímačem, není návrhovým průtokem soustavy. Instalační návod pro provedení s vestavěným záložním ohřívačem požaduje nejméně **20 l** vody. [LG – Engineering Product Data Book, MFL66101114, kapitola Hydraulic Performance](https://cms.intermetal.bg/storage/uploads/2022/07/20/62d7c8195b938PDB-R32-heatpump-KR_ThermaV_SplitR32_50Hz_HP_EU_MFL66101114_5BPU0-03DNov.2021_compressed.pdf), [LG – instalační návod, objem a expanze](https://www.manualslib.com/manual/3447006/Lg-Therma-V-Hn091mr.html?page=99).

Pět výměníků fan-coilů obsahuje dohromady pouze **5,99 l** vody (3 × 1,13 + 0,80 + 1,80 l). Při uzavření jejich ventilů navíc tento objem přestává být průtočně dostupný. Pitná voda v zásobníku TV o objemu 400 l se do tohoto požadavku vůbec nezapočítává.

Navrhuje se proto **objemová nádoba přibližně 50 l v sérii ve vratné větvi prostorového topení/chlazení**. Referenční výrobek **Regulus PS 50 ZC, kód 21717**, má skutečný objem 51 l, hrdla G 1", parotěsnou izolaci a rozsah 5–95 °C / nejvýše 4 bar. Vyhovuje vodě 7/12 i 45/40 °C a soustavě jištěné na 3 bar. Nejde o nádrž pitné vody. Dva návarky se využijí pro sériové zapojení, ostatní se zaslepí podle návodu. Rozměry s izolací Ø480 × 579 mm; pro zavěšení uvažovat hmotnost naplněné nádoby přibližně 90 kg a přístup k odvzdušnění. Její osazení a potrubí dosud nejsou vloženy do půdorysů. [Regulus – PS 50 ZC](https://www.regulus.cz/cz/akumulacni-nadrz-ps-50-zc.21717).

Mezi přívodem k rozdělovači a vratným sběračem **před objemovou nádobou** bude diferenční obtok. Referenčně **Caleffi 519500, G 3/4", nastavitelný 10–60 kPa**, nikoli vysokotlaká varianta 519504. Obtok i nádoba musí zůstat dostupné při uzavření všech pěti místních ventilů. Nastavení obtoku a čerpadla musí při této zkoušce zajistit nejméně 15 l/min přes hydrobox a nádobu; samotné osazení obtoku průtok nezaručuje. Za výchozí bod se uvažuje otevření přibližně 20 kPa, konečná hodnota se určí z charakteristiky ventilu a měřením. [Caleffi – řada 519, charakteristiky a seřízení](https://raccoltar.caleffi.it/prodotti/prod519/01007_it.pdf).

Objem 51 l zajišťuje rezervu proti minimu LG, ale nepotvrzuje konkrétní minimální dobu běhu kompresoru. Ta závisí na jeho modulaci, hysterezi a okamžité zátěži; při uvádění do provozu se ověří četnost startů a odmrazování.

#### 4.2.2. Zapojení

Hydrobox s vestavěným čerpadlem → **třícestný přepínací ventil TV** → buď pět paralelních fan-coilů, nebo výměník zásobníku QUANTUM. Vratná voda z fan-coilů a z jejich obtoku prochází sériovou 51l nádobou; vratná voda z výměníku TV se připojí až za ní. Společná vratná větev vede přes magnetický odlučovač nečistot a předepsaný filtr do hydroboxu. Doplní se uzávěry, plnění, vypouštění a odvzdušnění přístupných nejvyšších míst. Mezi pojistným zařízením a chráněnou částí nesmí běžná poloha servisních uzávěrů zrušit jejich propojení.

Toto zapojení neohřívá celý chladicí buffer při každém letním nabíjení TV. Pro samostatnou větev TV však musí být před objednáním ověřen i její dostupný vodní objem a odpor. QUANTUM ve zveřejněném listu neuvádí objem vody výměníku ani jeho tlakovou charakteristiku. List Hu.Ray pro stejně označený Q7 400 WWM se shodnou plochou 4,7 m² a rozměry uvádí **25 l** a ztrátu **186 kPa při 5,6 m³/h**; kvadratický přepočet na 0,948 m³/h vychází přibližně 5,3 kPa. Jde pouze o podpůrný údaj pro předběžný návrh, **nikoli o potvrzení parametrů dodávky QUANTUM**. Dodavatel má potvrdit objem a skutečnou charakteristiku výměníku. Součet dostupné vody ve výměníku, příslušném potrubí a hydroboxu musí i v režimu TV splnit nejméně 20 l; výměník sám nemusí mít 20 l, pokud vyhovuje součet. Pokud by dostupný objem nedosáhl minima LG, doplní se objem do této větve samostatně. [Hu.Ray – Q7 WWM, srovnávací výrobní podklad](https://huray.hu/ckfinder/userfiles/files/Huray%20T%C3%A1rol%C3%B3k/WWM/HRQ7WWM02.pdf).

Hydraulický oddělovač ani druhé oběhové čerpadlo se v základní variantě **nepřidávají**. Dvoutrubkový sériový buffer je objemová nádoba, nikoli čtyřhrdlové hydraulické oddělení se samostatným sekundárním čerpadlem.

#### 4.2.3. Předběžné dimenze a tlaková kontrola

Pro vodu a krátké domovní trasy se předběžně volí vícevrstvé potrubí s kyslíkovou bariérou: společná vedení **32 × 3 mm, světlost 26 mm**; samostatné větve k SL 400 a SL 600 **20 × 2 mm, světlost 16 mm**; větev k SL 1000 **26 × 3 mm, světlost 20 mm**. Dodržují se tím minima IVAR 14 / 16 / 20 mm pro modely 400 / 600 / 1000. Průměr závitu připojení G 3/4" Eurokonus není světlostí celé větve. Příslušné Eurokonus přechody musí odpovídat vybranému potrubnímu systému.

| Kontrolní vedení | Průtok pro kontrolu | Součet délky přívodu a zpátečky | Rychlost | Ztráta přímého potrubí |
|---|---:|---:|---:|---:|
| Společné vedení, světlost 26 mm | 0,948 m³/h | 20 m | 0,50 m/s | 3,0 kPa |
| Větev k SL 600, světlost 16 mm | 0,300 m³/h | 20 m | 0,41 m/s | 4,1 kPa |
| Větev k SL 1000, světlost 20 mm | 0,450 m³/h | 20 m | 0,40 m/s | 2,9 kPa |

Tabulka je **výpočet předběžného rozsahu, nikoli zaměření tras nebo nastavení průtoků místností**. Použita voda při přibližně 10 °C, Darcy–Weisbach, hladké potrubí a součinitel tření podle Blasia; místní odpory nejsou zahrnuty. K těmto hodnotám je pro kontrolu rezervováno dalších 50 % na místní odpory potrubí, 10 kPa na společné armatury/nádobu/filtr, 10 kPa na rozdělovač a vyvážení a přibližně 6,5 kPa na výměník SL 1000 při 0,450 m³/h. Plně otevřený ventil IVAR.139 má Kvs 3,60; při tomto průtoku přidá přibližně 1,6 kPa. Kontrolní nejnepříznivější cesta tak vychází přibližně **37 kPa**, oproti katalogově dostupným přibližně **72 kPa**. Pro zvolené předpoklady je vestavěné čerpadlo dostatečným výchozím řešením; katalogový údaj čerpadla i rezervu je nutné ověřit pro skutečné nastavení a konečné trasy.

Průtok místnosti se určí z její skutečné ztráty/zátěže, přibližně **q [l/h] = 860 × P [kW] / ΔT [K]**. Není správné současně nastavit katalogové maximální průtoky všech fan-coilů: jejich součet při 45/40 °C je 2,748 m³/h a odpovídá vyššímu tepelnému výkonu než tato sestava TČ. Při menším součtu průtoků větví doplní potřebný průtok hydroboxu obtok. Konečné vyvážení po místnostech zůstává navázané na výpočet zátěží.

Hodnota 0,948 m³/h při spádu 5 K odpovídá přenosu přibližně 5,5 kW. Při návrhu souběhu kompresoru a elektrického dohřevu se ověří také celkový přenášený výkon, průtok a přípustný spád; uvedená tlaková kontrola sama nepotvrzuje přenos součtu 5,5 + 6 kW při stejném spádu a průtoku.

Navazující kontrola VYT-03 používá návrhově korigované ztráty a delší 30m větve (součet přívodu a zpátečky). Součet bilančních průtoků vychází **825 l/h**, nejnepříznivější cesta asi **34,5 kPa** proti dostupným 71,6 kPa. Při průtoku zdrojem 948 l/h doplňuje obtok asi 123 l/h; při přívodu 40 °C vychází smíšená zpátečka přibližně 35,6 °C. Obtok proto ovlivňuje skutečný teplotní spád zdroje. Rozdělení průtoků pro chodby je pouze bilanční, dokud nebude doložena skutečná cesta dodávky jejich tepla. Rozsah měřidel vyvážení musí pokrýt i zhruba 6 l/min horní větve a malé průtoky koupelny. Skutečné trasy, armatury a průtok při zavřených ventilech zůstávají předmětem dopracování a měření.

#### 4.2.4. Referenční příslušenství a kompatibilita

Jde o návrh příslušenství ke koordinaci a objednání, nikoli o tvrzení, že je již součástí dodávky hlavních zařízení.

| Položka | Množství a referenční řešení | Ověření / podmínka |
|---|---|---|
| Oběh a expanze topné vody | Vestavěné čerpadlo, 8l expanze a 3bar pojistný ventil LG | Druhé čerpadlo ani další topnou expanzi nyní nepřidávat; ověřit konečný objem a statickou výšku podle kap. 9 |
| Objemová nádoba | 1× Regulus PS 50 ZC, 51 l | Vhodná pro topení i chlazení; sériově ve vratné prostorové větvi |
| Diferenční obtok | 1× Caleffi 519500 | Zajistit změřených ≥15 l/min při uzavřených jednotkách; zaizolovat i armaturu |
| Rozdělovač se sběračem | 1×, pět větví, společná připojení přibližně DN25 | Pro chlazení, s možností měření/vyvážení malých průtoků a parotěsnou izolací; konkrétní výrobek podle rozsahu průtoků |
| Ventilové sady FCU | 5× **IVAR.139, V20139**, 2cestný ventil s 230V elektrotermickou hlavicí a regulačním šroubením | Výrobce určuje pro SL/SLI; včetně izolace. Sada IVAR.661 je pro SLS a nenahrazuje ji |
| Místní regulace | 5× **IVAR.644, ECA644II**, pro dvoutrubkový systém | Řízení DC motoru a 230V výstup Y1 pro uvedenou hlavici; běžný termostat pro třírychlostní AC motor není náhradou |
| Podlahové podpěry | 5 sad **IVAR.LC 0605, LC0605II** | Podpěry jsou samostatné příslušenství; model počítá s 80mm prostorem pod skříní |
| Ohřev TV – přepínání | 1× **LG OSHA-3V** | LG uvádí pro tuto řadu; přepínací ventil, nikoli směšovací ventil. Ověřit G1" přechody, orientaci a 230V SPDT zapojení podle dodávky |
| Ohřev TV – čidlo a řízení | 1× **LG PHLTA** | Včetně tankového čidla **PHRSTA0** a prvků pro spínání dohřevu; stejné čidlo nekupovat podruhé. Čidlo LG osadit do vhodné jímky QUANTUM |
| Chlazení hydroboxu | 1× **LG PHDPC**, s odvodem kondenzátu | Pro HN091MR.NK5; **PHDPB není správnou variantou pro tento hydrobox** |
| Pomocný dohřev TV | Předběžně **Dražice TJ 6/4" – 2,5 kW, 230 V**, se samostatným bezpečnostním termostatem | Elektricky pod limitem PHLTA 3 kW, závit odpovídá možnosti TJ uvedené QUANTUM. Před objednáním potvrdit zástavbovou délku 405 ±10 mm a odstup od výměníku; mechanická montáž zatím není ověřena. Běžné těleso 3,3 kW nelze prostě nahradit za 2,5 kW |
| Zabezpečení pitné vody | Redukce na předběžně 3 bar, zpětná armatura, pojistný ventil předběžně 6 bar, **pitná expanzní nádoba 25 l**, směšování TV proti opaření | Samostatný okruh pitné vody podle kap. 9; nespojovat s topnou 8l expanzí |
| Filtrace a servis | Magnetický odlučovač, předepsaný filtr, uzávěry, odvzdušnění, plnění a vypouštění | Dimenzovat na ≥0,95 m³/h a započítat skutečné odpory; záslepky, spojky a izolace podle montáže |
| Kondenzát | 5 odvodů FCU + odvod z vaničky hydroboxu | Gravitačně, případně čerpadla pouze podle skutečných výšek; kontrolovatelná ochrana proti zápachu a poruchové blokování chlazení |

Podklady pro kompatibilitu: [IVAR – ventilové sady, zejména str. 2–5](https://www.ivarcs.cz/www/storage/Folder_File/82001-84000/6992b5c5-1a6f-4872-8005-f4f477171877_file_csnavod-ivar-661-361-662-205-ventily.pdf), [IVAR – regulace, zejména str. 57–62](https://www.ivarcs.cz/storage/Folder_File/78001-80000/fc078428-b5f0-420e-8603-603d0b21f574_file_csnavod-instalace-regulace-fancoily-ivar-749-649-644-647-b3v-08-2024.pdf), [IVAR – podstavce LC0605II](https://www.ivarcs.cz/katalog/tepelna-technika/nosne-podstavce-p142556/), [LG – katalog příslušenství](https://www.intechna.cz/fotky81432/katalog/LG-ThermaV-Split-5-9%20kW-2022.pdf), [LG – návod PHLTA, limit dohřevu 3 kW](https://manuals.plus/m/c05fefe7fcedae3f6336e85b7820f6eef804f83637456fff6d2d24be7f8f5fa5), [Dražice – TJ 6/4"](https://www.dzd.cz/prislusenstvi/pro-ohrev-vody/elektricka-topna-jednotka-tj-6-4).

### 4.3. Venkovní umístění

Jednotka LG HU051MR.U44 je umístěna u východního uličního rohu, východně od garážového otvoru, s výfukem směrem do ulice. Garážový otvor začíná 700 mm od vnitřního líce východní suterénní stěny; mezi otvorem a jednotkou je 300 mm. Zadní strana jednotky je 300 mm před dokončenou fasádou a východní okraj přesahuje dokončený roh přibližně o 150 mm.

Jednotka bude osazena na únosnou konstrukci s omezením přenosu vibrací do domu. Osazení musí umožnit proudění vzduchu, servis a odvod vody z odmrazování. Umístění v blízkosti suterénních otvorů, garáže a přístupových tras bude koordinováno tak, aby voda nezpůsobovala namrzání používaných ploch.

Akustické posouzení zohlední konkrétní stanoviště, odrazy od fasád, okolní chráněné prostory a noční provoz. Údaje o hluku ze zkušebních podmínek výrobce samy o sobě nenahrazují posouzení instalace.

#### 4.3.1. Orientační kontrola sousedních domů – 27. 11. 2026

LG pro HU051MR.U44 uvádí **akustický výkon 60 dB(A), v tichém režimu 58 dB(A)**. Hladina tlaku **38 / 36 dB(A) v 5 m** je výrobcem vypočtena pro volné pole se směrovým činitelem Q = 2 a nulovou tónovou přirážkou; nejde o výsledek měření této instalace ani o doložené maximum ve všech provozních stavech. [LG – specifikace a poznámka pod tabulkou, str. 6](https://www.lg.com/bg/business/download/airsolution/THERMA%20V%20%28AWHP%29%20Split%20series%20leaflet%5B20240322_195422398%5D.pdf).

Z polohy jednotky u východního uličního rohu a katastrálních obrysů vycházejí následující **vodorovné vzdálenosti od středu jednotky k nejbližší fasádě**. Pro kontrolu je vodorovná vzdálenost snížena o 2 m jako konzervativní přiblížení prostoru před fasádou. U levého, výše položeného souseda je navíc použito investorem uvažované převýšení 4 m, tedy r = √((d − 2)² + 4²); skutečná výška kontrolního bodu u okna dosud není ověřena. U pravého souseda se převýšení neuvažuje. Nejde o zaměření skutečných kontrolních bodů u oken; stínění domem a účinky kamenné stěny nejsou započteny.

| Sousední dům | Vodorovně k fasádě | Kontrolní vzdálenost r | Odhad běžný režim | Odhad tichý režim |
|---|---:|---:|---:|---:|
| Pravý RD na parcele 107 | 14,74 m | 12,74 m | 32,9 dB(A) | 30,9 dB(A) |
| Levý RD na parcele 102, převýšení předběžně 4 m | 14,87 m | 13,48 m | 32,4 dB(A) | 30,4 dB(A) |

Výpočet: **Lp(r) = Lp(5 m) − 20 log10(r/5) + 3 dB**. Přidané 3 dB představují orientační příspěvek odrazu od vlastní fasády za jednotkou, nad rámec Q = 2 z podkladu LG. Je to zjednodušený odhad s geometrickým útlumem, nikoli úplný frekvenční výpočet; další odrazy, směrovost, souběh zdrojů a nejistota nejsou započteny. Při použití akustického výkonu 60 / 58 dB(A) odpovídá tato úvaha přibližně Q = 4.

Pro stacionární zdroj u obytné fasády vychází podle NV č. 272/2011 Sb. základní limit **50 dB(A) ve dne a 40 dB(A) v noci**; při prokázané tónové složce se snižuje o 5 dB, tedy na **45 / 35 dB(A)**. Noční hodnocení používá nejhlučnější hodinu. Chráněný prostor staveb je definován do 2 m před příslušnou částí fasády; samotná hranice parcely není automaticky kontrolním bodem tohoto limitu. [NV č. 272/2011 Sb., § 12 a příloha 3](https://www.zakonyprolidi.cz/cs/2011-272#p12), [zákon č. 258/2000 Sb., § 30 odst. 3](https://www.zakonyprolidi.cz/cs/2000-258#p30-3).

**Předběžný závěr:** pro zvolené rohové umístění vychází běžný režim přibližně 32–33 dB(A), tedy v tomto odhadu pod 35 dB(A) u obou sousedů. Ani bez předpokládaného převýšení levého souseda by jeho odhad nepřesáhl 32,8 dB(A). Tichý režim snižuje odhad o další 2 dB. Zbývá ověřit maximální akustický výkon, spektrum/tónovost, skutečné kontrolní body u oken a odrazy včetně kamenné stěny. V nastavení LG se musí ověřit, zda tichý režim může automaticky opustit při nedosažené teplotě; takový přechod nelze v noční bilanci ignorovat. Výkon vytápění a přípravy TV se musí při omezeném režimu zachovat nebo odpovídajícím způsobem řídit. Tato kontrola neuzavírá akustické posouzení ani nezaručuje splnění limitu za všech podmínek.

Samostatně ověřit vlastní pokoj 0.03: střed jeho uličního okna je od středu venkovní jednotky ve 3D přibližně **3,7 m**. Zajistit zejména omezení přenosu vibrací do domu a hluku k tomuto oknu; větší odstup sousedních domů tento vlastní komfortní požadavek neřeší.

## 5. Otopné a chladicí plochy

Budou použity svisle osazené ventilokonvektory **IVAR.SL DC** s regulovatelnými ventilátory, v parapetním provedení vzhledově odpovídajícím radiátoru. Navržené řídicí moduly a připojovací sady jsou uvedeny v kapitolách 4.2 a 8. [IVAR – provedení a příslušenství řady SL DC](https://www.ivarcs.cz/katalog/tepelna-technika/fancoil-ivar-sl-p142555/)

### 5.1. Rozmístění a typy

| Označení v této zprávě | Místnost | Typ | Umístění |
|---|---|---|---|
| FCU-01 | 0.01 Pokoj 1 | IVAR.SL DC 600 | U stěny mezi pokoji; začátek jednotky 750 mm od příčné stěny zahradních pokojů |
| FCU-02 | 0.02 Pokoj 2 | IVAR.SL DC 600 | Zrcadlově k FCU-01 na druhé straně dělicí stěny |
| FCU-03 | 0.03 Pokoj 3 | IVAR.SL DC 600 | Pod uličním oknem |
| FCU-04 | 0.05 Koupelna | IVAR.SL DC 400 | U stěny k pokoji 3, mezi prostorem dveří a sprchou |
| FCU-05 | 1.01 Obývací pokoj + KK | IVAR.SL DC 1000 | Na zahradní stěně, vystředěný mezi okny |

Umístění umožní přístup k filtrům, ventilům, elektrické části a odvodu kondenzátu. Při konečném osazení se ověří předepsané montážní odstupy, výška na podlahových podpěrách a průchodnost nasávání. Modelové mezery ve stavebním výkrese nejsou potvrzením montážních odstupů výrobce.

### 5.2. Katalogové údaje a koordinace rozměrů

| Typ | Šířka × výška bez nožek × hloubka [mm] | Topný výkon [kW] | Celkový / citelný chladicí výkon [kW] |
|---|---|---:|---:|
| SL DC 400 | 935 × 579 × 129 | 2,21 | 2,12 / 1,54 |
| SL DC 600 | 1 135 × 579 × 129 | 3,02 | 2,81 / 2,11 |
| SL DC 1000 | 1 535 × 579 × 129 | 4,32 | 3,71 / 2,90 |

Topné hodnoty platí pro vodu 45/40 °C a vzduch 20 °C; chladicí pro vodu 7/12 °C a vzduch 27 °C suchého / 19 °C vlhkého teploměru. Pro požadovaných 25 °C v létě je nutný přepočet. [IVAR – technický list SL DC, 03/2026, str. 2–3](https://www.ivarcs.cz/storage/Folder_File/82001-84000/360054f7-d649-40dc-bfc5-9bfc64f13a35_file_cstl-ivar-sl-fancoil.pdf)

Katalogové výkony nejsou tepelnými ztrátami místností. Při návrhu se doloží výkon každé jednotky při skutečných teplotách vody a přijatelných otáčkách ventilátoru, zejména v pokojích určených ke spaní. Součet katalogových výkonů jednotek neurčuje potřebný výkon tepelného čerpadla.

Příloha VYT-03 obsahuje první přepočet na 40/35/20 °C: odhadem **1,71 / 2,34 / 3,35 kW** maximálně pro SL400 / SL600 / SL1000. Nejde o výrobkový výběr. Referenční certifikovaný INNOVA SL600 při 45/40/20 °C dává 1,20 kW na nízké a 2,16 kW na střední rychlosti; totožnost konkrétní dodávky IVAR je nutné potvrdit. Horní SL1000 při nejnižším publikovaném průtoku 262 m³/h nemůže s přívodem 40 °C přenést více než teoretických 1,78 kW, zatímco bilanční potřeba horního podlaží je přibližně 2,05 kW. Pro návrhový stav proto nelze počítat s nejnižším průtokem. Akustický tlak SL600 26/34 dB(A) a SL1000 28/38 dB(A) při nízké/střední rychlosti je katalogový údaj v 1 m, nikoli doložení hluku v místě pobytu. [Eurovent – referenční SL600](https://www.eurovent-certification.com/en/catalog/program/certificate/participant/model/show/200275034).

Pro prostorovou koordinaci se používají rozměry skříní z tabulky a **80mm podlahové podpěry**, tedy celková výška 659 mm. Hydrobox má rozměry šířka × výška × hloubka **490 × 850 × 315 mm**; šířka vede podél schodišťové stěny, hloubka do koupelny. Venkovní jednotka má **950 × 834 × 330 mm** a zadní stranu 300 mm od dokončené fasády kvůli sání vzduchu. Zásobník TV má rozměry Ø710 × 1670 mm.

Rozměry kamen PISA RLU jsou 460 × 488 × 1441 mm. Předepsané požární odstupy a ochrana podlahy se koordinují samostatně podle kapitoly 8 a PBŘ.

V obývacím pokoji je mezi zahradními okny pouze 1000 mm; skříň SL 1000 široká 1535 mm proto přesahuje pod půdorysné šířky oken přibližně 268 mm na každé straně. Výškově je horní hrana jednotky 261 mm pod spodní hranou oken, takže nejde o kolizi s okny. Zachovat přístup a volný výfuk, bez zakrytí závěsy nebo nábytkem.

Hydrobox je zavěšen **spodní hranou 1300 mm nad hotovou podlahou**, horní hranou 2150 mm. Ke spodku nosného stropu zbývá 475 mm, takže je splněn požadavek 250 mm nad jednotkou. Návod dále požaduje 200 mm po stranách. **Směrem k zásobníku TV je zatím pouze 102,5 mm**; tato servisní mezera se musí při koordinaci upravit. [LG – instalační návod HN091MR.NK5, str. 61](https://www.lgklimaat.nl/media/reofgoez/installatie-handleiding-hn091mrnk5.pdf).

### 5.3. Návrhové teploty vody

| Režim | Přívod / zpátečka | Návrhové podmínky |
|---|---|---|
| Vytápění | **45/40 °C** | Venkovní teplota −15 °C, vnitřní 20 °C |
| Vytápění – prověřovaná nižší varianta | **40/35 °C** | Zimní varianta VYT-03; výkon při požadovaných otáčkách a skutečném průtoku potvrdit |
| Chlazení | **7/12 °C** | Vnitřní teplota 25 °C; venkovní návrhová +32 °C |

Vytápění bude řízeno ekvitermně: uvedený spád platí pro zimní návrhový stav, v mírnějším počasí se teplota přívodu snižuje. Konkrétní ekvitermní křivka se nastaví podle tepelných ztrát a výkonových charakteristik jednotek. Výkony fan-coilů a jejich hluk se ověří při skutečných provozních podmínkách; údaj 7/12 °C sám nepotvrzuje dosažení 25 °C v místnosti. Chladicí provoz předpokládá odvod kondenzátu a souvislé parotěsné izolace rozvodů i armatur. Při přípravě TV se teplota nabíjecí vody řídí samostatně podle zásobníku a jeho výměníku, nikoli spádem 45/40 °C pro místnosti.

Pro první zprovoznění nižší varianty se předpokládá přívod přibližně 36–40 °C a zachování možnosti 45/40 °C při nedostatečném výkonu či komfortu. Mez přívodu zohledňuje čidlo ve výměníku a 30°C blokovací práh ventilátoru; při přibližně 5K rozdílu vody nemá výměník opakovaně přecházet do blokace. Konečnou křivku nastavit podle měřených teplot a výkonu, nikoli pouze podle katalogového spádu. Snížením teploty vody se samo neřeší nedostatek přenosu tepla do chodeb.

## 6. Potrubní rozvody a kondenzát

### 6.1. Vodní okruh

Přívodní a vratné potrubí povede z hydroboxu k rozdělovači a jednotlivým jednotkám a stoupacím vedením do podkroví. Předběžné dimenze jsou v kapitole 4.2.3; přesné trasy, prostupy a vyvážení se doplní po stanovení zátěží a skutečných délek. Silné šipky ve stávajících výkresech vyjadřují propojení zařízení, nikoli skutečnou trasu potrubí.

Potrubní systém a armatury musí být vhodné pro střídavé vytápění a chlazení. U jednotek budou přístupné uzavírací a regulační prvky umožňující hydraulické vyvážení a samostatný servis. Uložení potrubí se navrhne s ohledem na dilataci, ochranu konstrukcí a omezení přenosu hluku.

### 6.2. Chladivové propojení

Mezi venkovní jednotkou a hydroboxem bude chladivové potrubí dle instalačního návodu vybrané sestavy. Při dopracování se ověří délka, převýšení, izolace a případná úprava náplně. Prostup obvodovou konstrukcí bude utěsněn proti vodě a proudění vzduchu a koordinován s požárními a akustickými požadavky stavby.

### 6.3. Odvod kondenzátu z fan-coilů

Letní provoz vyžaduje odvod kondenzátu od všech pěti jednotek. Přednostně se navrhne gravitační odvod se souvislým spádem a přístupem pro čištění; v místech bez potřebné výšky se vybere čerpadlo s řešením poruchového stavu. Napojení na kanalizaci bude řešeno se zdravotnětechnickou profesí včetně ochrany proti zápachu. Průchodnost a odtok se při uvedení do provozu ověří zkouškou. [IVAR – instalační návod, část odvodu kondenzátu](https://www.ivarcs.cz/storage/Folder_File/78001-80000/517b0f93-54f0-435a-9763-4f5305bea669_file_csnavod-instalace-fancoily-ivar-slc-rs-sls-nastenne.pdf)

Odvod se musí doplnit také do výkresů kanalizace. Pro každý fan-coil se ověří jeho výšková poloha vůči napojovacímu bodu. Předepsána je také vanička **LG PHDPC pod hydroboxem** a její odvod. Voda z odmrazování venkovní jednotky bude řešena samostatně s ochranou před zamrzáním a bez namrzání přístupových ploch.

Větrací jednotka **HERU 100 T EC-y2 v S.04** má rotační výměník a standardní odvod kondenzátu se u ní nenavrhuje. Chladné venkovní potrubí a další větve vedené v odlišných teplotních podmínkách vyžadují parotěsnou izolaci, aby se na nich voda nesrážela. Blízkost kanalizace v S.04 je výhodná pro případný potřebný odvod, ale nenahrazuje pět odvodů od chladicích jednotek v obytných místnostech. VZT nemá samostatný vodní chladič vytvářející další kondenzát.

## 7. Příprava teplé vody

Pro čtyři uživatele je potvrzen samostatný nepřímotopný zásobník pitné teplé vody **QUANTUM Q7-400-WWM**, umístěný v koupelně přízemí. Zásobník má velkoplošný výměník pro ohřev tepelným čerpadlem; není akumulační nádobou pro vytápění místností.

| Parametr zásobníku | Hodnota |
|---|---|
| Typ / kód výrobce | QUANTUM Q7-400-WWM / 860061 |
| Objem vody podle výrobkového listu | 400 l |
| Průměr včetně izolace / výška | 710 / 1 670 mm |
| Plocha výměníku | 4,7 m² |
| Statická tepelná ztráta podle energetického štítku | 66 W, tj. 1,584 kWh za 24 h ve zkušebních podmínkách |
| Energetická třída | B |
| Hmotnost prázdného zásobníku | 150 kg |
| Povrch ve styku s pitnou vodou | Smalt; ochrana hořčíkovou anodou |
| Izolace | Pevná PUR izolace 50 mm, vnější PVC plášť |
| Pomocný elektrický ohřev | Možnost doplnění; konkrétní těleso a jeho výkon se zkoordinují s LG |

[QUANTUM – výrobkový list řady Q7-WWM, včetně energetických štítků](https://quantumas.cz/files/2024/06/quantum_produktove-listy_q7-wwm-2.pdf). Statická ztráta je katalogový údaj pro energetický výpočet, nikoli předpověď skutečné celoroční spotřeby. Osazení vychází z výkresové části; pro připojení, čištění a výměnu anody se ověří servisní prostor podle návodu výrobce.

Přepínání mezi ohřevem zásobníku a prostorovou soustavou zajistí řízená armatura podle hydraulického schématu. Návrh ověří přenosový výkon výměníku při dostupné teplotě vody z TČ, dobu dohřevu a očekávaný odběrový profil domácnosti. Z objemu zásobníku samotného nelze určit dostatečnost zdroje ani dobu ohřevu.

Pro předběžné energetické hodnocení se uvažuje teplota zásobníku TV **55 °C**. Konečné nastavení, hygienický ohřev a jeho elektrický dohřev se určí podle zvolené sestavy a návodů výrobce; elektrický dohřev musí být zahrnut do energetické bilance. V základní variantě se **předběžně neuvažuje cirkulace TV**. Potvrdí se po ověření skutečných délek, vnitřních průměrů a objemů větví a čekací doby u nejvzdálenějšího odběru. Cirkulace TV je vratný rozvod pitné teplé vody a nesouvisí s oběhovým čerpadlem otopné soustavy. Připojení studené a teplé vody, zabezpečení zásobníku na straně pitné vody a odvod z pojistných armatur řeší část D.1.2 ZTI.

Ohřev celých 400 l z 10 na 55 °C představuje přibližně **20,9 kWh**; při hypotetickém stálém výkonu 5,5 kW trvá nejméně 3,8 h bez započtení ztrát. Jde o studený start celého zásobníku, nikoli běžný denní odběr ani slíbenou dobu dohřevu. Při nabíjení musí být topná voda teplejší než aktuální voda v zásobníku; katalogový výkon výměníku při 80/60 °C nelze použít pro TČ. Nastavení 55 °C v zásobníku a hygienický cyklus se ověří proti teplotní obálce LG při skutečné venkovní teplotě a možnostem elektrického dohřevu. Vestavěný 6kW dohřev hydroboxu a navrhovaná 2,5kW patrona pitné vody jsou dvě různá zařízení a nemají se zaměňovat.

Investor pro kontrolu potvrdil vyšší denní odběr **300 l vody smíchané na 40 °C** pro čtyři osoby. Při studené vodě 10 °C jde o **10,47 kWh/den**, se štítkovou ztrátou zásobníku o **12,05 kWh/den** bez ztrát rozvodů. Ideálních 400 l při 55 °C odpovídá 600 l při 40 °C; skutečný využitelný objem závisí na rozvrstvení a regulaci a není tímto doložen výrobkový odběrový profil.

VYT-03 počítá idealizované nabíjení při A−15/W55 výkonem zdroje 4,58 kW, přibližně **2,63 h/den**. Pokud se po tuto dobu netopí do místností a zbývající čas kompresor pracuje při W40, konzervativní případ se suterénem −15 °C vyžaduje přibližně **8,54 kWh/den prostorové pomoci**. Jde o optimistickou časovou bilanci při konstantním přenosu celého výkonu, nikoli garantovanou dobu nabití ani skutečný podíl elektřiny. Při suterénu +5 °C nebo při −5 °C venku tento idealizovaný součet vychází bez prostorového dohřevu; dokončení ohřevu TV však stále může potřebovat patronu.

Výkon při W55 neznamená ohřev zásobníku na 55 °C beze zbytku: při vyrovnání teplot spirály a vody přestup klesá k nule a při A−15/W60 není doložen tabulkový provoz. Přenosovou křivku QUANTUM a nastavení čidla musí potvrdit dodavatel. Pro chladné období je dostupná záložní varianta s prioritou prostorového vytápění a ohřevem TV patronou, kterou LG popisuje v návodu. Samostatná patrona **2,5 kW** dodá uvedených 12,05 kWh přibližně za **4,82 h/den**. To vyžaduje ověřené fyzické osazení patrony, regulaci LG/PHLTA a elektrické souběhy. Nabíjení TV má mít časové omezení a přestávky pro vytápění místností; jeden souvislý mnohahodinový výpadek vytápění se nepředpokládá. [LG – instalační nastavení priorit a časování TV](https://www.lgklimaat.nl/media/reofgoez/installatie-handleiding-hn091mrnk5.pdf).

## 8. Měření a regulace

Pracovní koncepce počítá s regulací teploty topné vody podle venkovních podmínek a s místními ovladači **IVAR.644 ECA644II** a ventily **IVAR.139 V20139**. V zimě bude požadováno 20 °C, v létě 25 °C. Ovladače řídí DC ventilátor a 230V hlavici Y1. Čidla vody T2 zůstanou osazena; automatické blokování ventilátoru při nevhodné teplotě vody je součástí řízení. Při nastavení ekvitermní křivky je nutné zohlednit výchozí topný práh 30 °C pro spouštění ventilátoru, aby jednotky při nižší teplotě přívodu nepřestaly nechtěně topit.

Požadavky na vytápění BO/C2 a chlazení CH/C1 jsou **bezpotenciálové kontakty nejvýše 1 A**, nikoli napájení zdroje. Pro návrh propojení se počítá s jejich logickým součtem zvlášť pro topení a chlazení přes oddělovací relé na podporovaný termostatový vstup LG. Napěťové výstupy Y1 jednotlivých jednotek se nespojují mezi sebou. Elektro doplní konkrétní svorkové schéma, napěťovou hladinu a relé včetně blokování protichůdných požadavků. Nejde o přímé propojení sběrnice IVAR se sběrnicí LG.

Provozní režim léto/zima musí být společný. IVAR umožňuje využít vstup CP v režimu CO/CC pro sezónní přepnutí; při centrálním zapojení mají být jednotlivé vstupy odděleny vlastními kontakty, **nelze prostě propojit vstupy CP všech jednotek paralelně**. Pokud se tento vstup využije pro sezónu, porucha odvodu kondenzátu musí jednotku zablokovat jiným samostatným obvodem s bezpečným uzavřením vodního ventilu. Součástí funkční zkoušky bude režim TV, přepínání léto/zima a porucha kondenzátu.

Regulace musí koordinovat činnost zdroje a místních ventilů, doběhy čerpadel, odmrazování, ohřev TV a přechod mezi topením a chlazením. Nebude připouštět provoz zdroje bez potřebného průtoku. Pro ložnicové pokoje se nastaví vhodný noční režim ventilátorů.

Při chlazení se zohlední vnitřní vlhkost a rosný bod. Kondenzace na výměníku je odváděna vaničkou a drenáží; rozvody a armatury mimo tento prostor musí být chráněny proti povrchové kondenzaci. Případná porucha odvodu kondenzátu musí mít stanovenou reakci regulace.

Doplňkovým zdrojem jsou navržena **HAAS+SOHN PISA RLU** na kusové dřevo, bez teplovodního výměníku, v poloze podle půdorysu 2.NP. Technický list uvádí jmenovitý výkon Pnom 5,0 kW, rozměry šířka × hloubka × výška 460 × 488 × 1441 mm, kouřovod Ø 150 mm a minimální tah 12 Pa. Minimální odstupy od hořlavých materiálů jsou 200 mm vzadu, 300 mm po stranách a 800 mm vpředu i ke stropu. [HAAS+SOHN – technický list PISA RLU, typ 291.12](https://www.nejenkrby.cz/materialy/0429112710000_TD.pdf)

Spaliny bude odvádět **Schiedel ABSOLUT**; kamna budou mít těsný externí přívod spalovacího vzduchu. Konečný průměr a provedení komína, napojení kouřovodu a trasa přívodu vzduchu se ověří pro tuto sestavu. Ochrana podlahy a přesné osazení budou koordinovány s PBŘ, návody výrobců a větráním. Místní regulace umožní při provozu kamen omezit dodávku tepla příslušným fan-coilem, aniž by se zrušila potřeba vytápění ostatních místností.

## 9. Expanzní a pojistná zařízení

Topný/chladicí okruh využije vestavěnou expanzní nádobu LG 8 l. Výrobce při výchozím předtlaku 1 bar uvádí celkový objem soustavy do 230 l a statickou výšku pod 7 m jako základní případ bez úpravy předtlaku. Předběžný součet 51 l buffer + 5,99 l fan-coily + přibližně 20–35 l potrubí + výměník TV a vnitřní objem hydroboxu bude pravděpodobně výrazně pod tímto objemem. Další topná expanze se tedy nyní nepředepisuje; konečný součet, skutečná statická výška, maximální teplota i nastavení se ověří podle grafu LG. Rozdíl výšek v uzavřené soustavě určuje tlakové poměry expanze, nepřičítá se přímo k tlakové ztrátě oběhového čerpadla.

Delší kontrolní rozvody VYT-03 obsahují asi 44 l vody; s 51l bufferem a FCU vychází prostorová větev asi 101 l. Po přičtení srovnávacího 25l výměníku TV a 10l rezervy zůstává součet kolem 136 l pod referenční hranicí LG. Jde o objem z kontrolních délek, nikoli změřený stav. Buffer při 5K využitelné hysterezi uchová pouze 0,297 kWh: proti přebytku 1 kW asi 18 minut, proti 3 kW asi 6 minut. Není tím potvrzen počet startů kompresoru.

**Zásobník pitné TV má samostatné zabezpečení.** Pro předběžný návrh se uvažuje redukovaný studený tlak 3 bar a pojistný ventil 6 bar. Mezi zpětnou armaturou a zásobníkem bude **průtočná pitná expanze 25 l**, referenčně **Reflex Refix DD 25, 7380400**, s průtočným připojením výrobce; případná servisní armatura Flowjet nesmí zrušit funkci zabezpečení. Tento typ se osazuje do **studeného přívodu**, nikoli do horkého výstupu nebo topné vody. Výchozí tovární předtlak 4 bar se upraví na hodnotu odpovídající redukovanému tlaku. [Reflex – Refix DD 25, 7380400](https://reflex-winkelmann.com/nl/producten/7380400).

Pro 400 l vody ohřáté z 10 na 55 °C vychází dilatace přibližně 5,7 l, při ohřevu na 65 °C přibližně 7,8 l. Při předtlaku a studeném tlaku 3 bar a kontrolním horkém tlaku 5,5 bar poskytne 25l nádoba přibližně **25 × [1 − (3+1)/(5,5+1)] = 9,6 l** příjmového objemu, což pokrývá i přibližně 20% rezervu pro uvedený ohřev na 65 °C. Tento výsledek platí pro stanovené tlaky; při jiném tlaku vodovodu, hygienické teplotě nebo objemu rozvodu se velikost přepočte. Nastavení pojistného ventilu se ověří proti štítku skutečně dodaného zásobníku a všem armaturám. Pojistný odvod bude kontrolovatelný; na výstupu TV se navrhne termostatické směšování proti opaření.

Před uvedením do provozu budou stanoveny plnicí tlak, předtlak nádoby a nastavení ochranných funkcí. Odvod z pojistných prvků bude kontrolovatelný a bezpečně zaústěný. Zabezpečení pitné vody v zásobníku bude řešeno odděleně od uzavřeného topného okruhu.

## 10. Izolace, voda v soustavě a provozní údržba

Vodní rozvody používané pro chlazení budou souvisle izolovány proti kondenzaci včetně armatur, spojů a detailů závěsů. Izolace musí mít uzavřenou parotěsnou vrstvu; její tloušťka se stanoví podle teplot, vlhkosti, průměru potrubí a prostředí vedení. Izolují se rovněž přívody k jednotkám podle montážních pokynů. [IVAR – instalační návod, hydraulické připojení a izolace](https://www.ivarcs.cz/storage/Folder_File/78001-80000/517b0f93-54f0-435a-9763-4f5305bea669_file_csnavod-instalace-fancoily-ivar-slc-rs-sls-nastenne.pdf)

Před napuštěním se okruh vyčistí a propláchne. Kvalita plnicí vody a případné přísady budou odpovídat požadavkům všech připojených zařízení. Druh a dávkování chemických přípravků se neurčuje bez ověření jejich slučitelnosti.

Po instalaci se provedou předepsané zkoušky těsnosti, odvzdušnění, hydraulické vyvážení a funkční zkoušky vytápění, chlazení, odvodu kondenzátu a přípravy TV. Nastavení a skutečné průtoky budou zaznamenány. Provozní údržba zahrne filtry, výměníky, drenáže, armatury a kontrolu tlakových poměrů.

## 11. Požadavky na související profese

### 11.1. Stavební část

- Koordinovat podpory venkovní jednotky, kotvení hydroboxu a únosnost podlahy pod naplněným zásobníkem TV.
- Připravit a utěsnit prostupy, vedení do podkroví a přístupné servisní prostory.
- Aktualizovat skutečné rozměry zařízení a ověřit odstupy od oken, nábytku, dveří a sanitárních předmětů.
- Vyřešit samostatné osazení kamen, spalinovou cestu a přívod spalovacího vzduchu v příslušné části dokumentace.

### 11.2. Elektro

Sestava LG je v citované variantě jednofázová, 220–240 V / 50 Hz; elektrický dohřev představuje samostatně posuzovanou významnou zátěž. [LG – elektrické údaje](https://www.lg.com/gr/business/download/airsolution/Therma_V_R32_Split_Leaflet%5B20220621_225825898%5D.pdf) Stávající zakreslení třífázového přívodu k TČ se proto musí koordinovat s konečným zapojením venkovní jednotky a hydroboxu.

Profese elektro doplní potřebné přívody, jištění, ochrany, odpojování, komunikaci a regulaci podle výrobních návodů a výpočtu instalace. Posoudí příkon a souběhy kompresoru, dohřevu, případné patrony zásobníku a ostatních spotřebičů domu. Fan-coily a případná čerpadla kondenzátu budou zahrnuty do napájení a ovládání. Parametry kabelů a ochranných prvků zde nejsou předepsány.

Kontrolní souběh při A−15/W40: přibližně 2,39 kW příkon kompresorové sestavy podle COP 2,09, k tomu až 6 kW dohřev a 2,5 kW patrona TV, tedy přibližně **10,9 kW před ostatními spotřebiči**. Nejde o maximum příkonu ve všech stavech. Jednofázové přívody je nutné ověřit po jednotlivých fázích a případně řídit souběhy; celkový třífázový příkon domu sám neprokazuje vhodné rozložení těchto spotřebičů.

### 11.3. Zdravotnětechnické instalace a větrání

- Připojit zásobník TV, řešit jeho zabezpečení, případnou cirkulaci a napouštění otopné soustavy.
- Doplnit odvod kondenzátu od pěti fan-coilů a řešení vody z venkovní jednotky.
- Koordinovat odvod z pojistných armatur.
- Převzít návrhové údaje větrání z části D.1.2 VZT pro tepelnou a chladicí bilanci a ověřit provoz při používání kamen.

## 12. Technické údaje a tepelná bilance

| Parametr | Pracovní hodnota / stav |
|---|---|
| Počet koncových jednotek | 5 |
| Funkce soustavy | Vytápění, chlazení a příprava TV |
| Vnitřní návrhové teploty | 20 °C v zimě / 25 °C v létě |
| Zásobník TV / počet osob | QUANTUM Q7-400-WWM, 400 l / 4 osoby |
| Suterén | Nevytápěný |
| Kamna | Doplňková, bez propojení s vodním okruhem |
| Výpočtová venkovní teplota | −15 °C v zimě / +32 °C v létě |
| Tepelná ztráta domu | VYT-02 s λD: 4,68 / 4,30 kW; VYT-03 s návrhovou korekcí λ: **4,80 / 4,40 kW** při suterénu −15 / +5 °C, venku −15 °C |
| Letní citelná a celková chladicí zátěž | **DOPLNIT výpočtem** |
| Návrhové teploty topné a chladicí vody | Prověřovaná varianta **40/35 °C**, možnost 45/40 °C; konečné otáčky/hluk FCU potvrdit / 7/12 °C chlazení |
| Průtoky a tlakové ztráty | Zdroj 0,948 m³/h; bilanční větve 0,825 m³/h; cesta asi 34,5 kPa pro kontrolní délky VYT-03; skutečné trasy a vyvážení dopracovat |
| Prostorový bod bivalence | Při W40 asi −15,8 / −17,4 °C, při W45 asi −15,2 / −16,9 °C pro suterén −15 / +5 °C; orientační průsečíky bez TV, nikoli zákazy dohřevu |
| Objem soustavy a objemová nádoba | FCU 5,99 l; návrh Regulus PS 50 ZC / 51 l v prostorové větvi; konečný objem potrubí a výměníku QUANTUM potvrdit |
| Provozní teplota TV a doba dohřevu | Předběžně 55 °C; 300 l/den při 40 °C, asi 12,05 kWh/den se štítkovou ztrátou. Ideální nabíjení při A−15/W55 asi 2,63 h; skutečný přenos a dokončení na 55 °C potvrdit, patrona 2,5 kW zůstává součástí návrhu |
| Roční potřeba tepla a elektrické energie | **DOPLNIT energetickým výpočtem** |

Při návrhu teplot vody je cílem co nejnižší teplota v topném režimu a vhodně zvolená teplota v režimu chlazení při splnění vnitřních podmínek. Katalogové teploty z kapitoly 5 slouží pouze k identifikaci uvedených výkonů. Bez výpočtů nelze prohlásit, že zvolená sestava dosahuje návrhových teplot ve všech místnostech nebo stanovit její roční spotřebu.

### 12.1. Zjednodušená zimní bilance

Příloha **D.1.2.1-VYT-02 – Zjednodušený výpočet tepelné ztráty** obsahuje reprodukovatelný ustálený odhad z aktuální geometrie a skladeb. Započítává obvodové stěny, konstrukční otvory, šikmé a vodorovné části podhledu, podlahu nad suterénem i samostatnou podlahu pod schody. Ztráta nevytápěného suterénu se nepřičítá podruhé. Vnitřní schodiště propojuje vytápěná podlaží; předpokládá se vzduchové oddělení suterénu.

Hlavní předpoklady: interiér +20 °C, exteriér a konzervativně i suterén −15 °C; normální větrání 240 m³/h, referenční účinnost 77 %; dodatečná provozní infiltrace 0,10 h⁻¹ z hrubého objemu obálky; přirážka na tepelné mosty ΔU = 0,05 W/(m²·K). Aktuální požadavek λ izolací je 0,040 W/(m·K); pro střešní izolace se předpokládá 10 % dřevěných prvků. Kladné odpory zdiva, MIAKO, potěrů a desek se zanedbávají. Nad vodorovným podhledem se konzervativně uvažuje studená dutina a nepřičítá se další izolace mezi krokvemi nad ní. Pro okna platí Uw = 1,20, pro dosud nevybrané vstupní dveře se předpokládá Ud = 1,50 W/(m²·K). Tepelné zisky od osob, spotřebičů, slunce, zásobníku TV ani kamen se nezapočítávají.

| Případ při venkovní teplotě −15 °C | Odhad ztráty domu |
|---|---:|
| Suterén −15 °C, normální větrání | **4,68 kW** |
| Suterén 0 °C | 4,40 kW |
| Suterén +5 °C | 4,30 kW |
| Suterén +10 °C | 4,21 kW |
| Boost 300 m³/h, ostatní předpoklady základní | 4,85 kW |
| Kombinovaný nepříznivý případ: účinnost 65 %, infiltrace 0,20 h⁻¹, ΔU = 0,10 a λ izolací +10 % | 6,32 kW |

Pro kontrolu koncových jednotek se ztráta chodby 0.04 rozdělila podle ploch mezi čtyři přízemní FCU a ztráty 1.02 a 1.03 se přiřadily FCU obývacího pokoje. Takto vycházejí rozpočtové výkony přibližně **0,77 / 0,77 / 0,87 / 0,26 / 2,00 kW** pro místnosti **0.01 / 0.02 / 0.03 / 0.05 / 1.01**. Součet je 4,68 kW. Jejich katalogové maximální výkony při 45/40/20 °C mají rezervu; výkon při nejnižších otáčkách tím není doložen. Orientační součet průtoků větví při spádu 5 K je 0,81 m³/h; průtok hydroboxem musí nadále zajistit obtok podle kapitoly 4.2 a chlazení může vyžadovat jiné průtoky.

Rozdělení výkonu společných prostor je pouze bilanční. **Nepotvrzuje udržení 20 °C v chodbách a WC bez těles při zavřených dveřích.** Rovněž nejde o normový výpočet podle ČSN EN 12831-1 ani zaručenou horní mez ztráty. Výsledek závisí zejména na skutečné těsnosti, tepelných mostech, návrhových U skladeb a zimní účinnosti VZT včetně rozvodů v suterénu. Nezahrnuje ztráty rozvodů, ohřev TV a zátop po útlumu. Chladicí zátěže, roční energie a bod bivalence z této bilance nevyplývají.

### 12.2. Navazující technická kontrola VYT-03

Příloha **D.1.2.1-VYT-03 – Technické ověření vytápění a přípravy TV** doplňuje prostorový bod bivalence, denní bilanci TV a kontrolu přenosu do místností. Pro tuto kontrolu jsou navíc zvýšeny λ minerálních vat o 7 % a EPS o 3 %; jde o zjednodušenou návrhovou variantu podle přílohy 5 části C vyhlášky 264/2020 Sb., nikoli o změnu tlouštěk modelu. Odhad ztráty je 4,80 kW při venku/suterénu −15/−15 °C, 4,40 kW při −15/+5 °C a 3,23 kW při −5/+5 °C. Současně s těmito hodnotami se nesmějí bez rozlišení používat starší hodnoty s λD z VYT-02.

Početně byly zkontrolovány kontrolní hydraulické cesty, průtoky a obtok, objem/expanzní rezerva, denní energie vyššího odběru TV a základní kapacita dohřevu. Přenos do chodeb/WC, tichý pracovní bod horní FCU a boční mezera hydroboxu nevyšly jako hotové řešení. Ověřený výběr přesné dodávky FCU a přenosovou charakteristiku zásobníku nemůže nahradit přibližný přepočet teplot. Přesné podmínky otevřených bodů jsou uvedeny ve VYT-03 a v závěru níže.

## 13. Závěr a dopracování

Pracovní návrh stanovuje koncepci s pěti fan-coily, potvrzenou sestavou LG a samostatným zásobníkem TV. Podle zadání investora neobsahuje podlahové vytápění ani vytápění suterénu. Letní provoz zahrnuje také potřebné odvodnění a izolace chladicích rozvodů.

Před uzavřením návrhu budou dopracovány zejména:

1. Rozhodnutí o konkrétním vytápění chodeb a WC: doložený přenos s přijatými teplotami, nebo změna rozdělení koncových zařízení; pouhé připsání ztráty sousedním FCU nestačí. Ověřit předpoklady těsnosti, tepelných mostů a čisté zimní účinnosti VZT. Samostatně doplnit letní chladicí zátěže.
2. Výrobkový výběr přesného IVAR při 40/35 °C a skutečném průtoku: nízké otáčky pokojů a vyšší potřebný průtok horní FCU, hluk v místě pobytu. Konečná ekvitermní křivka, modulace a počty startů podle dat LG a zprovoznění.
3. Dokončení hydraulického schématu podle kapitoly 4.2: skutečné délky, armatury, rozsahy měřidel vyvážení, objem/odpor výměníku QUANTUM a měření průtoku při otevřených i zavřených FCU a při TV.
4. QUANTUM: nabíjecí výkon/UA při dostupné teplotě vody, poloha čidla LG a kompatibilita zástavby 2,5kW patrony; časování TV/topení a dokončení na 55 °C. Denní energetická potřeba pro potvrzený odběr 300 l při 40 °C je již vyčíslena ve VYT-03, není však změřenou dobou nabití.
5. Materiál a dimenze rozvodů, trasy kondenzátu a podrobnosti regulace.
6. Dořešení bočních servisních odstupů zvýšeného hydroboxu, umístění bufferu a expanzní nádoby TV, koordinace jednofázového elektrického napájení a konkrétního schématu řízení.
7. Posouzení venkovního osazení a hluku a doplnění navazujících výkresů.

Po dopracování těchto bodů bude možné potvrdit konečné parametry zařízení a nahradit označení **DOPLNIT** konkrétními návrhovými údaji.
