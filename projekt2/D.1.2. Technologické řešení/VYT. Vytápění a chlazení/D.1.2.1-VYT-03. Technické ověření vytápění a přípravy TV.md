# D.1.2.1-VYT-03. Technické ověření vytápění a přípravy TV

**RD Lažánky – LG HU051MR.U44 + HN091MR.NK5, pět IVAR.SL DC, QUANTUM Q7-400-WWM**

## 1. Výsledek kontroly

Malé tepelné čerpadlo lze ponechat jako základ bivalentní soustavy s automatickým elektrickým dohřevem. Provoz 40/35 °C je vhodnou výchozí variantou, avšak splnění všech teplot a hluku současným rozmístěním pěti FCU **není potvrzeno**. Hlavní neuzavřené body jsou dodávka tepla do chodeb a WC, tichý výkon horní FCU, nabíjecí charakteristika skutečného zásobníku a boční servisní prostor hydroboxu. Tato příloha rozlišuje početní ověření, odhad a zkoušku na stavbě; není autorizovaným normovým projektem.

| Kontrola | Výsledek |
|---|---|
| Výkon zdroje pro vytápění | V uvedeném základním odhadu vychází; malá rezerva, automatický dohřev zůstává součástí návrhu |
| Energetická bilance TV pro 4 osoby, vyšší odběr | Vyčíslena; za návrhových mrazů počítat s elektřinou také pro TV |
| FCU při 40/35 °C, maximální otáčky | Odhad rezervy vychází; nejde o výrobcem potvrzený výběr při daném průtoku |
| Chodby a WC při 20 °C | Současná koncepce bez vlastního tělesa neprokazuje potřebné předání tepla |
| Horní FCU na nejnižším publikovaném průtoku vzduchu | 40 °C přívod nestačí pro celý horní výkon ani při ideálním přenosu |
| Čerpadlo a dimenze potrubí | Vyhovují kontrolním délkám; skutečné trasy a tlaková zkouška zbývají |
| Objem prostorové větve a topná expanze | Dostatečná předběžná rezerva; průtok při zavřených FCU ověřit měřením |
| Větev zásobníku TV | Přesný objem, odpor a výkon skutečného QUANTUM potvrdit dodavatelem |
| Umístění hydroboxu | Nevyhovuje boční servisní mezeře vedle zásobníku |

## 2. Zimní vstupy a aktualizace vodivostí

Přebírají se geometrie a konzervativní předpoklady přílohy VYT-02. Pro tuto kontrolu je navíc použita zjednodušená návrhová korekce deklarovaných λ: minerální vata +7 %, EPS +3 %, XPS beze změny. Jde o transparentní citlivostní variantu podle možnosti uvedené v příloze 5 části C vyhlášky 264/2020 Sb.; výrobkový návrhový přepočet může dát jinou hodnotu. Původní odhad VYT-02 s λD se tím zpětně nepřepisuje. Nadále se neuvažují kladné odpory zdiva a dalších pevných vrstev ani vnitřní a solární zisky.

| Venkovní / suterén [°C] | 1.NP [kW] | 2.NP [kW] | Celkem [kW] | LG při W40 [kW] | LG při W45 [kW] |
|---|---:|---:|---:|---:|---:|
| -15 / -15 | 2.75 | 2.05 | 4.80 | 4.99 | 4.85 |
| -15 / +5 | 2.36 | 2.05 | 4.40 | 4.99 | 4.85 |
| -5 / +5 | 1.77 | 1.46 | 3.23 | 5.50 | 5.50 |

LG výkony jsou maximální, včetně odmrazování, nikoli v tichém režimu. Nesmějí být zaměňovány s minimální modulací nebo zaručeným výkonem ve skutečné instalaci. Suterén se samostatně nevytápí; jeho vlastní ztráta se k podlaze nepřičítá podruhé.

### Bod bivalence – pouze prostorové vytápění

Při konstantní teplotě vody vychází z průsečíku výkonové a ztrátové křivky:

| Přívod [°C] | Suterén [°C] | Orientační venkovní bod bivalence [°C] |
|---:|---:|---:|
| 40 | -15 | -15.8 |
| 40 | +5 | -17.4 |
| 45 | -15 | -15.2 |
| 45 | +5 | -16.9 |

Toto **není teplota zákazu elektrodohřevu**. Příprava TV odebírá čas, předpoklady ztráty jsou přibližné a provozní rezerva je malá. Automatická pomoc musí být dostupná také nad vypočteným bodem. Kamna jsou dobrovolný doplněk; v těchto výsledcích nemají připsaný výkon.

## 3. Fan-coily při 40/35 °C

Publikované maximální výkony IVAR jsou při 45/40/20 °C. Pro kontrolu 40/35/20 °C se používá pouze první přiblížení poměrem logaritmických rozdílů teplot voda–místnost: LMTD(40/35/20) / LMTD(45/40/20) = 0,776. Není to výstup výběrového programu. Změna průtoku vody mění i přestup tepla; odhad nelze použít jako potvrzený výkon při nejnižších otáčkách.

| FCU | Vlastní místnost [W] | Bilanční podíl chodeb/WC [W] | Celkem [W] | Odhad maxima 40/35 [W] | Průtok pro celkový podíl při 5 K [l/h] |
|---|---:|---:|---:|---:|---:|
| 0.01, SL 600 DC | 631 | 162 | 793 | 2342 | 136 |
| 0.02, SL 600 DC | 631 | 162 | 793 | 2342 | 136 |
| 0.03, SL 600 DC | 697 | 198 | 895 | 2342 | 154 |
| 0.05, SL 400 DC | 191 | 79 | 269 | 1714 | 46 |
| 1.01, SL 1000 DC | 1755 | 294 | 2049 | 3351 | 352 |

Přiřazení chodeb do tabulky je výhradně bilanční. Nevytváří cestu, kterou se do nich teplo dostane. Průtoky jsou potřebou pro daný výkon při ΔT 5 K, ne konečným vyvážením ventilů. Při nižším výkonu může být skutečná vratná teplota vyšší než 35 °C.

### Nízké otáčky a hluk

Certifikovaný referenční INNOVA AirLeaf SL600 má při 45/40/20 °C výkon 1,20 kW na nízké a 2,16 kW na střední rychlosti. Shodují se rozměry a maximální výkon s publikovaným IVAR.SL600; totožnost konkrétní dodávky IVAR však musí být potvrzena. Pro nízkou rychlost vychází první odhad při 40/35 °C přibližně 931 W, s dodatečnou kontrolní srážkou 15 % asi 791 W. To pokrývá vlastní ztrátu pokojů v základním případě, ale neprokazuje předání připsané části ztráty chodby. Srážka 15 % není výrobcem garantovanou tolerancí.

Pro SL1000 je publikovaný nejnižší průtok vzduchu 262 m³/h. I kdyby výstupní vzduch dosáhl celých 40 °C, odnesl by nejvýše **1782 W**, zatímco bilanční horní výkon je **2049 W**. Skutečný výstup je chladnější, takže nejnižší publikovaný průtok není řešením pro celé horní podlaží v návrhovém stavu. Při 479 m³/h a tomto výkonu by potřebný výstupní vzduch měl přibližně 32.6 °C; výkon na této rychlosti musí potvrdit výběr jednotky.

IVAR uvádí akustický tlak při nízké/střední rychlosti ve vzdálenosti 1 m: SL600 26/34 dB(A), SL1000 28/38 dB(A). Nejsou to hladiny u postele nebo sedačky a nejsou přímo zaměnitelné s akustickým výkonem. Reverberace, poloha a souběh s VZT nejsou doloženy. Splnění komfortního cíle 25 dB(A) v pokojích nelze z těchto údajů potvrdit; prosté odečtení útlumu volného pole v malé místnosti není dostatečné. Pokud má být tento cíl závazný i pro FCU, je třeba výběr při požadovaném výkonu a akustický návrh nebo měření.

### Teplota vyfukovaného vzduchu a regulace

Platí Tair,out = Troom + Q/(0,34·qair). Při vlastních ztrátách a nejnižším publikovaném průtoku:

| FCU | Potřebný výkon místnosti [W] | Průtok vzduchu [m³/h] | Potřebný výstup vzduchu [°C] |
|---|---:|---:|---:|
| 0.01 | 631 | 180 | 30.3 |
| 0.02 | 631 | 180 | 30.3 |
| 0.03 | 697 | 180 | 31.4 |
| 0.05 | 191 | 118 | 24.8 |
| 1.01 | 1755 | 262 | 39.7 |

Tabulka je energetická potřeba, nikoli potvrzený pracovní bod. Zejména v koupelně by nepřetržité vyfukování při malé ztrátě bylo vlažné; ventilátor má při uspokojeném požadavku omezit nebo ukončit činnost, nikoli zbytečně rozdmýchávat vzduch. Čidlo vody H2/T2 musí zůstat zapojené; ovladač blokuje ventilaci při nevhodné teplotě vody, v topení pod 30 °C. Zpočátku držet přívod přibližně 36–40 °C, aby při ΔT do 5 K zbývala rezerva nad blokovacím prahem, a křivku nastavit při zprovoznění. Hodnota 40/35 je varianta k ověření; možnost 45/40 zůstává pro mráz či nedostatečný komfort. U běžného SL nepoužít nastavení nočního režimu, které zakáže ventilátor, a současně nepředpokládat nucený katalogový výkon.

## 4. Místnosti bez FCU

Při 20 °C činí vlastní ztráta chodby 0.04 **600 W**, chodby 1.03 **275 W** a WC 1.02 **19 W**. Při stejné teplotě všech sousedních místností neexistuje hnací rozdíl pro přestup z interiéru. Přestupující vzduch o 20 °C také nemůže udržovat ztrátovou místnost na 20 °C bez dalšího zdroje. Samotná zásoba výkonu v pěti FCU tedy tento požadavek nesplňuje.

Obě chodby se pro nutnou podmínku sloučí do jedné cirkulační zóny. Přitéká do ní 120 m³/h z přízemních pokojů a čistých 40 m³/h z horního obývacího pokoje po odečtení kuchyňského odvodu. Není přidán nový větrací průtok. Otevřeným schodištěm se může vzduch míchat, ale samo o sobě nepřidává tepelný zdroj.

| Teplota chodeb [°C] | Ztráta chodeb [W] | Přenos větracím vzduchem z místností 20 °C [W] | Zbývá dodat stěnami nebo jinou cestou [W] |
|---:|---:|---:|---:|
| 20 | 875 | 0 | 875 |
| 18 | 825 | 109 | 716 |
| 16 | 775 | 218 | 557 |

Jde o nutnou energetickou podmínku, ne o výpočet skutečné teploty chodby. Pro ni chybí potvrzené tepelné odpory vnitřních příček a dveří, jejich stav otevření a proudění. Nelze pouze prohlásit, že snížení požadavku na 18 °C problém vyřeší. K uzavření návrhu je nutné buď doložit konkrétní přenos tepla při přijatých nižších teplotách, nebo upravit rozdělení koncových zařízení. Orientační přímý výkon pro chodby při 20 °C je asi 0,6 kW v 1.NP a 0,3 kW ve 2.NP; to je podklad pro rozhodnutí, nikoli pokyn k přidání těles. WC může využívat přenos ze skutečně vytápěné chodby, ale i jeho výsledná teplota musí být doložena. Současný model s pěti FCU nebyl touto kontrolou změněn.

## 5. Vyšší odběr TV a zimní časová bilance

Potvrzený odběr: čtyři osoby, **300 l/den při 40 °C**, studená voda 10 °C, zásobník 400 l při 55 °C. Ohřev spotřebované vody potřebuje **10.46 kWh/den**. Se štítkovou ztrátou 66 W (1.58 kWh/den) jde o **12.05 kWh/den**. Ztráty odboček a čekání na vodu nejsou zahrnuty; cirkulace se neuvažuje. Štítková ztráta není měřením skutečného denního provozu a zisk do koupelny se současně nezapočítává.

Ideálních 400 l při 55 °C odpovídá **600 l při 40 °C** smícháním se studenou vodou 10 °C. Denní odběr odpovídá **200 l vody 55 °C**. Skutečnou využitelnost snižují promíchání, teplotní rozvrstvení, regulace a špičkový odběr; nejde o certifikovaný odběrový profil zásobníku. Studený start celého zásobníku 10→55 °C je **20.93 kWh**, odlišný od běžného dne.

### Idealizovaná časová bilance kompresoru

V tabulce se celá denní energie TV dělí maximálním výkonem LG při výstupní vodě 55 °C. Po tento čas kompresor netopí do místností. Zbytek dne smí pro kontrolu pracovat na maximální výkon při 40 °C. Jde o optimistický výpočet doby nabíjení a dolní odhad potřebné pomoci v tomto konkrétním způsobu řízení; není garantován přenos výměníkem ani dokončení ohřevu na 55 °C.

| Venkovní / suterén [°C] | Teplo místnosti [kWh/den] | Ideální nabíjení TV [h/den] | Prostorová pomoc elektřinou při W40 [kWh/den] |
|---|---:|---:|---:|
| -15 / -15 | 115.2 | 2.63 | 8.54 |
| -15 / +5 | 105.7 | 2.63 | 0.00 |
| -5 / +5 | 77.5 | 2.19 | 0.00 |

Tento denní součet sám neprokazuje udržení teploty při dlouhém nepřerušeném nabíjení TV. LG umožňuje omezit délku jedné nabíjecí periody a vložit přestávku pro prostorové vytápění. Výchozí časování v citovaném návodu je 30 minut nabíjení / 30 minut přestávky; konkrétní firmware a nastavení ověřit. Nepředepisuje se jeden mnohahodinový blok bez vytápění místností.

### Dokončení ohřevu zásobníku

Výkon LG při W55 je výkon zdroje při teplotě jeho topné vody, nikoli výkon nabíjení zásobníku o teplotě 55 °C. Při stejné teplotě vody ve spirále a zásobníku přestup klesá k nule. Při A−15/W60 není v tabulce doložený výkon; nelze jej extrapolovat. Samotná plocha výměníku 4,7 m² nestačí k určení jeho výkonu při malém teplotním rozdílu. Proto musí zůstat součástí návrhu samostatná elektrická patrona TV a její regulace. Objem vody a tlaková charakteristika převzaté ze srovnatelného Hu.Ray nejsou potvrzením dodávky QUANTUM.

Celých 400 l při 45→55 °C potřebuje **4.65 kWh**; při 50→55 °C **2.33 kWh**. Skutečná energie poslední fáze závisí na rozvrstvení a poloze čidla.

Kapacitní záložní varianta: patrona 2,5 kW dodá celých 12.05 kWh za **4.82 h/den**. LG v návodu popisuje prioritu prostorového vytápění, při které TV přebírá patrona a kompresor se věnuje místnostem. Tím není nutné ani za mrazu spoléhat na obsluhu kamen. Vyžaduje to skutečně osazenou a mechanicky ověřenou patronu, správnou konfiguraci LG/PHLTA a dostatečné elektrické napájení. Jde o energetickou dostupnost, nikoli předpoklad, že se tak bude ohřívat celý rok. Hygienický režim a ochranu proti opaření stanoví návrh TV a návody výrobků.

## 6. Hydraulická kontrola

Kontrolní délky: společné potrubí 32×3 mm celkem 20 m přívod+zpátečka; každá větev celkem 30 m. Pokojové a koupelnová větev 20×2 mm, horní větev 26×3 mm. Nejsou to zaměřené trasy ani délky konceptuálních šipek v půdorysu. Tření je počítáno konzervativně pro vodu 10 °C s laminárním/turbulentním rozlišením. Přičteno 50 % potrubního tření na místní odpory, 10 kPa na společné armatury/filtr/nádobu a 10 kPa na rozdělovač a vyvážení. Odpor výměníku FCU je pouze kvadratický odhad z katalogového bodu, odpor ventilu z Kvs = 3,60.

| Větev | Průtok [l/h] | Rychlost [m/s] | Potrubí [kPa] | Výměník – odhad [kPa] | Celá cesta – odhad [kPa] |
|---|---:|---:|---:|---:|---:|
| 0.01 | 136 | 0.19 | 1.61 | 1.25 | 28.2 |
| 0.02 | 136 | 0.19 | 1.61 | 1.25 | 28.2 |
| 0.03 | 154 | 0.21 | 1.97 | 1.60 | 29.1 |
| 0.05 | 46 | 0.06 | 0.31 | 0.13 | 25.0 |
| 1.01 | 352 | 0.31 | 2.79 | 4.98 | 34.5 |

Nejnepříznivější kontrolní cesta **34.5 kPa** je pod disponibilní výškou přibližně **71.6 kPa** při 948 l/h. Druhé čerpadlo není pro tyto předpoklady potřeba. Výškový rozdíl podlaží se v uzavřeném okruhu nepřičítá k třecí tlakové ztrátě. Výsledek neplatí pro nezměřené dlouhé trasy nebo zanesené filtry bez kontroly skutečného průtoku.

Součet bilančních větví je **825 l/h**. Při průtoku hydroboxu 948 l/h projde obtokem asi **123 l/h**. Při přívodu 40 °C a návrhové ztrátě vyjde směšovaná zpátečka u zdroje asi **35.6 °C**, nikoli přesně 35 °C. Obtok tedy ovlivňuje skutečný pracovní bod. Při zavření větví musí obtok a buffer zajistit doporučené minimum LG 15 l/min; ověřit měřením, samotné nastavení 20 kPa není důkazem. Rozdělovač/ventily musí umět měřit přibližně 0,5–0,8 l/min u koupelny, 2–3 l/min u pokojů a asi 6 l/min u horní větve; běžná stupnice 0–5 l/min nemusí vyhovět celému rozsahu.

## 7. Dostupný objem, expanze a cyklování

Z kontrolních délek vychází potrubí **44.2 l**, prostorová větev s bufferem 51 l a výměníky FCU 5,99 l asi **101.2 l**. Jde o horní kontrolní délky, nikoli skutečný napuštěný objem. Při zavření FCU zůstává dostupný buffer a společná větev; samotný buffer přesahuje minimum LG 20 l. Pro režim TV se připojení vrací až za bufferem. Požadavek 20 l se vztahuje k dostupnému součtu výměníku TV, potrubí a hydroboxu; výměník sám nemusí mít 20 l, pokud součet minimum splní.

Se srovnávacím 25l výměníkem a další 10l objemovou rezervou vychází nejvýše přibližně **136 l**, pod referenčními 230 l LG pro vestavěnou 8l expanzi a odpovídající statickou výšku. Skutečný objem, výška a předtlak se před plněním ověří. Pitná 25l expanze zásobníku zůstává samostatná a není součástí této 8l nádoby.

Buffer 51 l při využitelné hysterezi 5 K uloží **0.297 kWh**. Například při přebytku 1 kW prodlouží běh asi o 18 minut, při 3 kW asi o 6 minut. Nejde o předpověď počtu startů: minimální modulace LG v daném bodě, celkový dostupný objem a regulační hystereze nejsou doloženy. Zdroj má reagovat na součet požadavků FCU; při nulovém požadavku nepokračovat zbytečně v prostorovém ohřevu, ale zachovat ochrany proti mrazu, odmrazování a doběhy. Nevypínat celý zdroj odpojením napájení.

## 8. Elektrické a prostorové podmínky

Při A−15/W40 a tabulkovém COP 2,09 činí příkon kompresorové sestavy asi **2.39 kW**. S plným 6kW dohřevem a patronou TV 2,5 kW může souběh dosáhnout asi **10.9 kW** před ostatními spotřebiči. Není to zaručené maximum příkonu instalace. Jde o jednofázové spotřebiče se samostatnými přívody podle návodů; nelze je bez kontroly seskupit na jednu fázi. Elektro musí ověřit přívody, fáze, jištění, hlavní jistič a případné omezení souběhů či stupňů dohřevu. Stávající symbol třífázového přívodu TČ sám neodpovídá ověřenému zapojení této splitové sestavy.

Modelová mezera vedle hydroboxu k zásobníku je **102.5 mm** v části, kde se jejich výšky překrývají. LG požaduje 200 mm po stranách. Chybí tedy **97.5 mm**. Poloha musí být upravena před potvrzením montáže; touto kontrolou se zařízení neposouvají. Horní odstup 475 mm je proti požadavku 250 mm dostatečný.

## 9. Uzavření kontroly a nezbytné podklady

Početně byly prověřeny zimní výkonová a denní bilance, přepočet 40/35 °C, nutné podmínky pro místnosti bez těles, kontrolní hydraulické cesty, objemy, základní expanzní rezerva a servisní mezera. Neuzavřené body se nerozepisují jako hotové ani jako požadavek na další PENB:

- **Rozhodnutí o chodbách/WC:** doložit konkrétní přenos tepla a výsledné teploty, nebo upravit rozdělení zdrojů v místnostech.
- **Výběr FCU:** výrobková identita IVAR/INNOVA, výkon při 40/35 °C a skutečném průtoku vody, potřebné otáčky a hluk v místě pobytu.
- **QUANTUM:** výkon/UA při vodě 50–55 °C, tlaková charakteristika, objem výměníku, poloha čidla a slučitelnost konkrétní 2,5kW patrony se zástavbou.
- **Provedení:** přesné trasy, měřicí rozsahy vyvážení, servisní mezera hydroboxu, elektrické přívody/fáze a schéma regulace.
- **Zprovoznění:** průtok při všech kombinacích ventilů včetně zavřených, časování TV/topení, spínání patrony, směšování TV, expanze, počet startů a hluk.
- **Další rozsah:** letní chladicí zátěže, skutečné trasy šesti kondenzátních odvodů a roční energie nejsou výsledkem této zimní kontroly. PENB řeší energetický specialista s těmito vstupy.

## Podklady

- [LG – výkonové tabulky](https://www.lg.com/content/dam/channel/wcms/hu/business/download/airsolution/2021_THERMA_V_%28AWHP%29_R32_Split_R410A_Split_leaflet_0302_FIN_20211102_223018918_.pdf); [LG – technický datový list, hydraulika a provozní obálka](https://cms.intermetal.bg/storage/uploads/2022/07/20/62d7c8195b938PDB-R32-heatpump-KR_ThermaV_SplitR32_50Hz_HP_EU_MFL66101114_5BPU0-03DNov.2021_compressed.pdf); [LG – instalační návod, řízení TV](https://www.lgklimaat.nl/media/reofgoez/installatie-handleiding-hn091mrnk5.pdf).
- [IVAR – technický list SL DC](https://www.ivarcs.cz/storage/Folder_File/82001-84000/360054f7-d649-40dc-bfc5-9bfc64f13a35_file_cstl-ivar-sl-fancoil.pdf); [IVAR – regulace](https://www.ivarcs.cz/storage/Folder_File/78001-80000/fc078428-b5f0-420e-8603-603d0b21f574_file_csnavod-instalace-regulace-fancoily-ivar-749-649-644-647-b3v-08-2024.pdf); [Eurovent – referenční INNOVA SL600](https://www.eurovent-certification.com/en/catalog/program/certificate/participant/model/show/200275034).
- [QUANTUM – Q7-WWM](https://quantumas.cz/files/2024/06/quantum_produktove-listy_q7-wwm-2.pdf). Srovnávací Hu.Ray je uveden v technické zprávě VYT-01, nenahrazuje potvrzení QUANTUM.
- [Vyhláška 264/2020 Sb., příloha 5, C.1 – návrhové vodivosti](https://www.zakonyprolidi.cz/cs/2020-264#prilohy).
- Stavební část dokumentace, skladby, příloha VYT-02 a návrhové průtoky VZT.
