# D.1.2.1-VYT-01. Vytápění a chlazení

## Technická zpráva – pracovní návrh

| Identifikační údaj | Hodnota |
|---|---|
| Stavba | RD Lažánky |
| Investor | Ing. Jiří Bobek |
| Stupeň dokumentace | DSP – pracovní návrh profesní části |
| Datum | 21. 11. 2026 |
| Zodpovědný projektant profese | **DOPLNIT** |
| Parcelní čísla a katastrální území | **DOPLNIT podle aktuální stavební dokumentace** |

Zpráva zachycuje potvrzený záměr investora a předběžné technické řešení. Označení **DOPLNIT** vymezuje údaje vyžadující výpočet nebo výběr konkrétního příslušenství. Výkonová dostatečnost soustavy bude doložena výpočtem tepelných ztrát a chladicích zátěží.

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
| Suterén | Bez aktivního vytápění a chlazení; výpočtová teplota se stanoví tepelnou bilancí |
| Počet uživatelů pro přípravu TV | 4 osoby |

### 2.3. Podklady

- Aktuální model `house2.py`, stavební výkresy a skladby konstrukcí.
- Výkresy `D.1.2.2-VYT-01. Vytápění a chlazení – půdorys 1.NP.pdf` a `D.1.2.2-VYT-02. Vytápění a chlazení – půdorys 2.NP.pdf` v adresáři `projekt2/D.1.2. Technologické řešení/VYT. Vytápění a chlazení/`.
- Koordinační podklady částí D.1.2 ELE – elektroinstalace, D.1.2 ZTI – zdravotně technické instalace a D.1.2 VZT – řízené větrání.
- Zadání investora: sestava LG, pět fan-coilů IVAR, vytápění i chlazení, zásobník TV 400 l, nevytápěný suterén a doplňková kamna.
- Výrobní podklady uvedené u příslušných zařízení níže.

Referenční zpráva `D1.7.00. technická zpráva.pdf` ze složky `PD_Zouhar` byla použita jako osnova. Její tepelné bilance, klimatické údaje a dimenze soustavy nejsou převzaty jako výpočet tohoto domu.

Pro dopracování jsou základními normovými podklady [ČSN EN 12831-1 – výpočet tepelného výkonu pro vytápění](https://csnonline.agentura-cas.cz/Detailnormy.aspx?k=505721) a [ČSN EN 12828+A1 – navrhování teplovodních otopných soustav](https://csnonline.agentura-cas.cz/Detailnormy.aspx?k=96137). Navazující požadavky, použitelné změny a rozsah dalších norem se upřesní podle konečného provedení zařízení.

## 3. Základní koncepční řešení

Venkovní jednotka tepelného čerpadla bude umístěna na uliční straně domu v návaznosti na suterénní průčelí. Vnitřní hydraulický modul a samostatný zásobník TV budou v koupelně 0.05 v přízemí. Jejich umístění vychází z výkresové části; osazovací a servisní prostory budou koordinovány s konkrétními výrobky.

Za hydraulickým modulem bude uzavřená dvoutrubková soustava s nuceným oběhem. Pět fan-coilů bude připojeno paralelně přívodním a vratným potrubím. Rozdělení větví pomocí rozdělovače nebo odboček se určí při dopracování hydraulického schématu.

Soustava bude mít společný režim vytápění nebo chlazení. Jednotlivé místnosti budou regulovány samostatně, avšak dvoutrubkové zapojení neumožní současné vytápění jedné místnosti a chlazení jiné. Při požadavku na ohřev TV bude tepelné čerpadlo přepnuto do režimu nabíjení zásobníku; konkrétní priority a časová omezení se nastaví při uvedení do provozu.

Chodby 0.04 a 1.03 a WC 1.02 nemají v současném rozmístění vlastní otopné těleso. Při výpočtu se prověří jejich teplotní režim a předávání tepla z navazujících prostorů. Samotná existence rekuperačního větrání nedokládá pokrytí jejich tepelné ztráty. Záměr s pěti jednotkami musí být posouzen pro všechny požadované vnitřní teploty.

## 4. Zdroj tepla a chladu

### 4.1. Potvrzené tepelné čerpadlo

Investorem je potvrzena sestava **LG THERMA V, venkovní jednotka HU051MR.U44 a vnitřní hydrobox HN091MR.NK5**. Jde o splitovou sestavu s chladivem R32 a chladivovým propojením mezi jednotkami. Výrobce uvádí jmenovitý topný výkon **5,50 kW při A7/W35**. Tato hodnota charakterizuje katalogový provozní bod, nikoli ověřený výkon při návrhové zimní teplotě konkrétní stavby. [Podklad LG – R32 Split Hydro Box, specifikace sestavy](https://www.lg.com/gr/business/download/airsolution/Therma_V_R32_Split_Leaflet%5B20220621_225825898%5D.pdf)

Výkonová dostatečnost potvrzené sestavy se ověří porovnáním výkonové křivky s tepelnou ztrátou domu při návrhové teplotě topné vody. Prověří se také minimální výkon, četnost spínání, odmrazování, souběh provozních požadavků a schopnost přípravy TV. V zimní bilanci se nebude předpokládat nezbytná obsluha doplňkových kamen.

Hydrobox obsahuje hydraulické a zabezpečovací prvky; pro tuto variantu katalog uvádí elektrický dohřev 6 kW ve dvou stupních, expanzní nádobu 8 l a pojistný ventil 3 bar. Zapojení a využití dohřevu, bod bivalence a dostatečnost vestavěné expanze se ověří při návrhu celé soustavy. [Technické údaje LG](https://www.lg.com/gr/business/download/airsolution/Therma_V_R32_Split_Leaflet%5B20220621_225825898%5D.pdf)

### 4.2. Hydraulické uspořádání

Hydraulický návrh zajistí požadovaný průtok a dostupný objem vody i při částečně nebo úplně uzavřených místních regulačních ventilech. Potřeba objemové nádoby, hydraulického oddělení nebo obtoku bude určena podle požadavků LG a výpočtu soustavy. Jejich provedení ani objem nejsou v této fázi předepsány.

Objem 400 l v zásobníku TV představuje pitnou vodu a nenahrazuje požadovaný objem vody v otopném okruhu. Do vodního objemu otopné soustavy se zahrnou pouze její skutečně připojené části včetně výměníku zásobníku.

Budou navrženy uzávěry pro servis, filtrace a odlučování nečistot, odvzdušnění a vypouštění. Návrh armatur a oběhového čerpadla bude vycházet z tlakových ztrát nejnepříznivější větve a požadovaných průtoků.

### 4.3. Venkovní umístění

Jednotka bude osazena na únosnou konstrukci s omezením přenosu vibrací do domu. Osazení musí umožnit proudění vzduchu, servis a odvod vody z odmrazování. Umístění v blízkosti suterénních otvorů, garáže a přístupových tras bude koordinováno tak, aby voda nezpůsobovala namrzání používaných ploch.

Akustické posouzení zohlední konkrétní stanoviště, odrazy od fasád, okolní chráněné prostory a noční provoz. Údaje o hluku ze zkušebních podmínek výrobce samy o sobě nenahrazují posouzení instalace.

## 5. Otopné a chladicí plochy

Budou použity svisle osazené ventilokonvektory **IVAR.SL DC** s regulovatelnými ventilátory, v parapetním provedení vzhledově odpovídajícím radiátoru. Výběr řídicího modulu a připojovací sady bude součástí dodávky. [IVAR – provedení a příslušenství řady SL DC](https://www.ivarcs.cz/katalog/tepelna-technika/fancoil-ivar-sl-p142555/)

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

**Koordinační poznámka:** dříve použité rozměry 1 030 × 690 × 210, 830 × 690 × 210 a 1 430 × 690 × 210 mm vycházejí z přepravních rozměrů a neodpovídají skříním nyní zvolených typů. Před uzavřením výkresové dokumentace je nutné opravit modelové rozměry, zahrnout podlahové podpěry a znovu prověřit polohy u oken, dveří a sprchy. U této zprávy nebyly půdorysy ani model automaticky měněny.

### 5.3. Návrhové teploty vody

| Režim | Přívod / zpátečka | Návrhové podmínky |
|---|---|---|
| Vytápění | **45/40 °C** | Venkovní teplota −15 °C, vnitřní 20 °C |
| Chlazení | **7/12 °C** | Vnitřní teplota 25 °C; venkovní návrhová +32 °C |

Vytápění bude řízeno ekvitermně: uvedený spád platí pro zimní návrhový stav, v mírnějším počasí se teplota přívodu snižuje. Konkrétní ekvitermní křivka se nastaví podle tepelných ztrát a výkonových charakteristik jednotek. Výkony fan-coilů a jejich hluk se ověří při skutečných provozních podmínkách; údaj 7/12 °C sám nepotvrzuje dosažení 25 °C v místnosti. Chladicí provoz předpokládá odvod kondenzátu a souvislé parotěsné izolace rozvodů i armatur. Při přípravě TV se teplota nabíjecí vody řídí samostatně podle zásobníku a jeho výměníku, nikoli spádem 45/40 °C pro místnosti.

## 6. Potrubní rozvody a kondenzát

### 6.1. Vodní okruh

Přívodní a vratné potrubí povede z hydroboxu v přízemí k jednotlivým jednotkám a stoupacím vedením do podkroví. Přesné trasy, prostupy, materiál a dimenze budou doplněny po stanovení průtoků a tlakových ztrát. Silné šipky ve stávajících výkresech vyjadřují propojení zařízení, nikoli skutečnou trasu potrubí.

Potrubní systém a armatury musí být vhodné pro střídavé vytápění a chlazení. U jednotek budou přístupné uzavírací a regulační prvky umožňující hydraulické vyvážení a samostatný servis. Uložení potrubí se navrhne s ohledem na dilataci, ochranu konstrukcí a omezení přenosu hluku.

### 6.2. Chladivové propojení

Mezi venkovní jednotkou a hydroboxem bude chladivové potrubí dle instalačního návodu vybrané sestavy. Při dopracování se ověří délka, převýšení, izolace a případná úprava náplně. Prostup obvodovou konstrukcí bude utěsněn proti vodě a proudění vzduchu a koordinován s požárními a akustickými požadavky stavby.

### 6.3. Odvod kondenzátu z fan-coilů

Letní provoz vyžaduje odvod kondenzátu od všech pěti jednotek. Přednostně se navrhne gravitační odvod se souvislým spádem a přístupem pro čištění; v místech bez potřebné výšky se vybere čerpadlo s řešením poruchového stavu. Napojení na kanalizaci bude řešeno se zdravotnětechnickou profesí včetně ochrany proti zápachu. Průchodnost a odtok se při uvedení do provozu ověří zkouškou. [IVAR – instalační návod, část odvodu kondenzátu](https://www.ivarcs.cz/storage/Folder_File/78001-80000/517b0f93-54f0-435a-9763-4f5305bea669_file_csnavod-instalace-fancoily-ivar-slc-rs-sls-nastenne.pdf)

Odvod se musí doplnit také do výkresů kanalizace. Pro každý fan-coil se ověří jeho výšková poloha vůči napojovacímu bodu. Voda z odmrazování venkovní jednotky bude řešena samostatně podle venkovních podmínek.

## 7. Příprava teplé vody

Pro čtyři uživatele je zadán samostatný zásobník TV o objemu **400 l**, umístěný v koupelně přízemí. Bude vybrán nepřímotopný zásobník určený pro spolupráci s tepelným čerpadlem. Typ, rozměry, tepelná ztráta a parametry výměníku jsou **DOPLNIT**.

Přepínání mezi ohřevem zásobníku a prostorovou soustavou zajistí řízená armatura podle hydraulického schématu. Návrh ověří přenosový výkon výměníku při dostupné teplotě vody z TČ, dobu dohřevu a očekávaný odběrový profil domácnosti. Z objemu zásobníku samotného nelze určit dostatečnost zdroje ani dobu ohřevu.

Pro předběžné energetické hodnocení se uvažuje teplota zásobníku TV **55 °C**. Konečné nastavení, hygienický ohřev a jeho elektrický dohřev se určí podle zvolené sestavy a návodů výrobce; elektrický dohřev musí být zahrnut do energetické bilance. V základní variantě se **předběžně neuvažuje cirkulace TV**. Potvrdí se po ověření skutečných délek, vnitřních průměrů a objemů větví a čekací doby u nejvzdálenějšího odběru. Cirkulace TV je vratný rozvod pitné teplé vody a nesouvisí s oběhovým čerpadlem otopné soustavy. Připojení studené a teplé vody, zabezpečení zásobníku na straně pitné vody a odvod z pojistných armatur řeší část D.1.2 ZTI.

## 8. Měření a regulace

Pracovní koncepce počítá s regulací teploty topné vody podle venkovních podmínek a s místní regulací fan-coilů. V zimě bude požadováno 20 °C, v létě 25 °C. Ovladače jednotek budou řídit ventilátor a vodní ventil podle teploty místnosti a společného provozního režimu. Konkrétní ovladače, ventily a způsob předávání požadavku zdroji se doplní.

Regulace musí koordinovat činnost zdroje a místních ventilů, doběhy čerpadel, odmrazování, ohřev TV a přechod mezi topením a chlazením. Nebude připouštět provoz zdroje bez potřebného průtoku. Pro ložnicové pokoje se nastaví vhodný noční režim ventilátorů.

Při chlazení se zohlední vnitřní vlhkost a rosný bod. Kondenzace na výměníku je odváděna vaničkou a drenáží; rozvody a armatury mimo tento prostor musí být chráněny proti povrchové kondenzaci. Případná porucha odvodu kondenzátu musí mít stanovenou reakci regulace.

Doplňkovým zdrojem jsou navržena **HAAS+SOHN PISA RLU** na kusové dřevo, bez teplovodního výměníku, v poloze podle půdorysu 2.NP. Technický list uvádí jmenovitý výkon Pnom 5,0 kW, rozměry šířka × hloubka × výška 460 × 488 × 1441 mm, kouřovod Ø 150 mm a minimální tah 12 Pa. Minimální odstupy od hořlavých materiálů jsou 200 mm vzadu, 300 mm po stranách a 800 mm vpředu i ke stropu. [HAAS+SOHN – technický list PISA RLU, typ 291.12](https://www.nejenkrby.cz/materialy/0429112710000_TD.pdf)

Spaliny bude odvádět **Schiedel ABSOLUT**; kamna budou mít těsný externí přívod spalovacího vzduchu. Konečný průměr a provedení komína, napojení kouřovodu a trasa přívodu vzduchu se ověří pro tuto sestavu. Ochrana podlahy a přesné osazení budou koordinovány s PBŘ, návody výrobců a větráním. Místní regulace umožní při provozu kamen omezit dodávku tepla příslušným fan-coilem, aniž by se zrušila potřeba vytápění ostatních místností.

## 9. Expanzní a pojistná zařízení

Dimenzování a nastavení expanze se doloží ze skutečného objemu vodního okruhu, statické výšky, teplotního rozsahu a přípustných tlaků. Vestavěná expanzní nádoba uvedená v kapitole 4 se započte do výpočtu; její dostatečnost není touto zprávou prohlášena za ověřenou.

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
| Zásobník TV / počet osob | 400 l / 4 osoby |
| Suterén | Nevytápěný |
| Kamna | Doplňková, bez propojení s vodním okruhem |
| Výpočtová venkovní teplota | −15 °C v zimě / +32 °C v létě |
| Tepelná ztráta jednotlivých místností a domu | **DOPLNIT výpočtem** |
| Letní citelná a celková chladicí zátěž | **DOPLNIT výpočtem** |
| Návrhové teploty topné a chladicí vody | 45/40 °C vytápění, ekvitermní regulace / 7/12 °C chlazení |
| Průtoky a tlakové ztráty | **DOPLNIT hydraulickým výpočtem** |
| Bod bivalence a využití elektrického dohřevu | **DOPLNIT** |
| Objem soustavy a případná objemová nádoba | **DOPLNIT** |
| Provozní teplota TV a doba dohřevu | Předběžně 55 °C; dobu dohřevu a hygienický režim ověřit po výběru zásobníku |
| Roční potřeba tepla a elektrické energie | **DOPLNIT energetickým výpočtem** |

Při návrhu teplot vody je cílem co nejnižší teplota v topném režimu a vhodně zvolená teplota v režimu chlazení při splnění vnitřních podmínek. Katalogové teploty z kapitoly 5 slouží pouze k identifikaci uvedených výkonů. Bez výpočtů nelze prohlásit, že zvolená sestava dosahuje návrhových teplot ve všech místnostech nebo stanovit její roční spotřebu.

## 13. Závěr a dopracování

Pracovní návrh stanovuje koncepci s pěti fan-coily, potvrzenou sestavou LG a samostatným zásobníkem TV. Podle zadání investora neobsahuje podlahové vytápění ani vytápění suterénu. Letní provoz zahrnuje také potřebné odvodnění a izolace chladicích rozvodů.

Před uzavřením návrhu budou dopracovány zejména:

1. Výpočty tepelné ztráty a chladicí zátěže včetně místností bez vlastní koncové jednotky.
2. Ověření výkonu TČ v návrhových podmínkách, teplot vody, výkonů fan-coilů a přijatelných otáček ventilátorů.
3. Hydraulické schéma, průtoky, objem vody, expanze a zabezpečení.
4. Typ 400l zásobníku, jeho výměník, regulace a bilance přípravy TV.
5. Materiál a dimenze rozvodů, trasy kondenzátu a podrobnosti regulace.
6. Koordinace skutečných rozměrů zařízení, montážních odstupů a jednofázového elektrického napájení.
7. Posouzení venkovního osazení a hluku a doplnění navazujících výkresů.

Po dopracování těchto bodů bude možné potvrdit konečné parametry zařízení a nahradit označení **DOPLNIT** konkrétními návrhovými údaji.
