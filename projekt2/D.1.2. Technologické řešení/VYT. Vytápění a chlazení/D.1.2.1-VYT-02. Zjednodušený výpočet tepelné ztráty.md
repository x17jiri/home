# D.1.2.1-VYT-02. Zjednodušený výpočet tepelné ztráty

**RD Lažánky – orientační ustálená zimní bilance**

Výsledná ztráta při 20/−15 °C a suterénu −15 °C je **4.68 kW**. Jde o konzervativní kontrolu velikosti zdroje a otopných těles, nikoli o výpočet podle ČSN EN 12831-1. Zvolená míra infiltrace, tepelné mosty, účinnost větrání a U dveří nejsou změřené ani konečně doložené; výsledek proto není zaručenou horní mezí skutečné ztráty.

## 1. Hranice a předpoklady

Obálku tvoří půdorys vnějšího líce zdiva 8.74 × 8.99 m (78.57 m²), obvodové stěny a dvě šikmé části podhledu s vodorovným středem. Střešní přesahy neleží nad vytápěným prostorem a nezvětšují plochu tepelné obálky. Stěna mezi podlažími není venkovní konstrukcí; výška mezistropu je započtena v obvodové stěně 1.NP.

Suterén je pro hlavní kontrolu nahrazen venkovním prostředím −15 °C. Započítává se proto ztráta podlahou nad suterénem, nikoli znovu jeho obvodovými stěnami a základovou deskou. Pod schody je samostatně zohledněna izolovaná dřevěná podlaha. Vnitřní schodiště mezi vytápěnými podlažími není venkovním otvorem. Předpokladem je vzduchové oddělení nevytápěného suterénu; netěsný nebo otevřený průchod by vyžadoval další bilanci proudění.

| Parametr | Hodnota |
|---|---:|
| Vnitřní / venkovní teplota | +20 / −15 °C |
| Větrání, normální provoz | 240 m³/h |
| Zpětné získávání tepla | 77 % – referenční hodnota HERU, předpoklad pro tuto bilanci |
| Dodatečná provozní infiltrace | 0,10 h⁻¹; nejde o n50 |
| Hrubý objem uvnitř obálky pro infiltraci | 428.3 m³ |
| Přirážka na tepelné mosty | ΔU = 0,05 W/(m²·K) celé hrubé obálky |
| Okna / vstupní dveře | Uw = 1,20 / předpoklad Ud = 1,50 W/(m²·K) |
| Podíl dřeva v obou střešních izolačních vrstvách | předpoklad 10 %, λ dřeva 0,18 W/(m·K) |

Objem pro infiltraci je záměrně hrubý, tedy včetně vnitřního zdiva a mezistropu; nejde o čistý vzduchový objem používaný při kontrole větrání. Nezapočítávají se tepelné zisky od osob, spotřebičů, slunce, zásobníku TV ani kamen. Není přidána další paušální výkonová rezerva. Bilance neobsahuje ohřev TV, zátop po útlumu ani samostatné ztráty potrubí a VZT vedených suterénem.

## 2. Skladby a zjednodušené U

Pro izolace se přebírají aktuální požadavky modelu. Deklarované λ jsou zde použity jako výpočtový předpoklad; konečný návrhový přepočet podle vlhkosti a provedení není proveden. Kladný odpor zdiva, potěrů, MIAKO, dřevěných desek, omítek a vzduchových vrstev je vynechán, což zvyšuje odhad prostupu tepla. U = 1 / (Rsi + Σ d/λ + Rse). U vrstvy s dřevem se používá konzervativní účinná vodivost 0,9λ izolace + 0,1λ dřeva.

| Konstrukce | Započtená izolace | U [W/(m²·K)] |
|---|---|---:|
| Obvodová stěna | 200 mm minerální vaty, λ 0.040 | 0.193 |
| Šikmá střecha | 200 + 200 mm vaty, λ 0.040; dřevo 10 % | 0.132 |
| Vodorovný podhled | 200 mm vaty, λ 0.040; dřevo 10 % | 0.260 |
| Podlaha nad suterénem | 120 mm EPS, λ 0.040 + 30 mm vaty, λ 0.040 | 0.244 |
| Podlaha pod schody | 200 mm vaty, λ 0.040 | 0.187 |

Povrchové odpory: stěny 0,13 + 0,04; střecha 0,10 + 0,04; podlaha mezi vytápěným a nevytápěným vzduchem 0,17 + 0,17 m²·K/W. Nad vodorovným podhledem se konzervativně předpokládá studená větraná dutina; izolace mezi krokvemi nad touto dutinou se proto nepřičítá. Tepelná přirážka ΔU se vztahuje na plochu včetně otvorů, nikoli pouze neprůsvitné konstrukce; i u podlahy zůstává vztažena k rozdílu 35 K v citlivostních případech s teplejším suterénem.

## 3. Celková bilance

Prostup Q = A·U·ΔT; větrání Q = 0,34·q·(1−η)·ΔT; infiltrace Q = 0,34·n·V·ΔT. Hodnota 0,34 má jednotku Wh/(m³·K). Odvodní průtoky nejsou k přívodním přičteny podruhé. Ztráta větráním se přiřazuje přívodním místnostem, odkud přestupuje vzduch do odvodních místností.

| Složka | Plocha [m²] | Ztráta [W] |
|---|---:|---:|
| Obvodové stěny bez otvorů | 150.24 | 1017 |
| Okna | 14.08 | 591 |
| Vstupní dveře | 2.45 | 128 |
| Šikmé části střechy | 70.98 | 329 |
| Vodorovný podhled | 21.22 | 193 |
| Běžná podlaha nad suterénem | 75.67 | 648 |
| Podlaha pod schody | 2.90 | 19 |
| Tepelné mosty | — | 591 |
| Infiltrace | — | 510 |
| Řízené větrání po rekuperaci | — | 657 |
| **Celkem** | | **4683** |

Zaokrouhlené řádky se mohou od celku lišit o jednotky wattů.

## 4. Orientační rozdělení po místnostech

Plochy otvorů jsou převzaty z konstrukčních otvorů, nikoli z rozměru dveřního křídla. Obvodové plochy se přiřazují podle polohy místností. Zbývající pruhy pod vnitřním zdivem a u vnějších líců se přiřazují nejbližší místnosti na síti nejvýše 100 mm. Schodiště patří chodbám. Tím jsou zahrnuty i konstrukce mimo čisté podlahové polygony a součet odpovídá celé obálce. Síť ovlivňuje pouze rozdělení mezi místnosti, nikoli celkovou ztrátu. Vnitřní přestupy při rozdílných teplotách místností se zde neřeší.

| Místnost | Čistá podlaha [m²] | Stěna bez otvorů [m²] | Okna [m²] | Ztráta [W] |
|---|---:|---:|---:|---:|
| 0.01 Pokoj 1 | 12.86 | 20.79 | 2.59 | 617 |
| 0.02 Pokoj 2 | 12.86 | 20.79 | 2.59 | 617 |
| 0.03 Pokoj 3 | 15.78 | 25.02 | 2.18 | 680 |
| 0.04 Chodba | 13.52 | 20.96 | 0.00 | 584 |
| 0.05 Koupelna | 6.25 | 6.18 | 0.53 | 186 |
| 1.01 Obývací pokoj + KK | 52.82 | 45.77 | 6.19 | 1715 |
| 1.02 Zachod | 1.20 | 0.00 | 0.00 | 18 |
| 1.03 Chodba | 6.47 | 10.72 | 0.00 | 266 |

Čistá plocha chodby 0.04 v tabulce nezahrnuje samostatnou dřevěnou podlahu pod schody; její konstrukce je přesto zahrnuta do ztráty této chodby.

## 5. Kontrola zařízení

Pro rozpočtovou kontrolu se ztráta chodby 0.04 dělí mezi čtyři přízemní fan-coily podle čistých ploch jejich místností. Ztráty WC 1.02 a chodby 1.03 se přidávají k obývacímu pokoji. Toto rozdělení dokládá pouze výkonový rozpočet, **nikoli schopnost vytápět chodby a WC přes uzavřené dveře**. Při shodné teplotě přívodních a odvodních místností vzduch přestupující mezi nimi nepokrývá jejich vlastní tepelné ztráty. Udržení 20 °C v prostorech bez těles zůstává neověřené.

| FCU | Vlastní místnost [W] | Podíl společných prostor [W] | Rozpočtový výkon [W] | Max. katalog 45/40/20 [W] | Voda při ΔT 5 K [l/h] |
|---|---:|---:|---:|---:|---:|
| 0.01, SL 600 DC | 617 | 157 | 774 | 3020 | 133 |
| 0.02, SL 600 DC | 617 | 157 | 774 | 3020 | 133 |
| 0.03, SL 600 DC | 680 | 193 | 873 | 3020 | 150 |
| 0.05, SL 400 DC | 186 | 76 | 262 | 2210 | 45 |
| 1.01, SL 1000 DC | 1715 | 284 | 1999 | 4320 | 344 |

Katalogové maximální výkony FCU mají proti tomuto odhadu rezervu. List IVAR však nedokládá tyto výkony při nejnižších otáčkách. Nelze je poměrově přepočítat podle průtoku vzduchu ani tím prohlásit splnění hlukového cíle. Uvedené průtoky vody jsou orientační potřeby místností při 5 K; obtok musí nadále zajistit minimální průtok zdrojem a při chlazení mohou být potřeby jiné.

LG HU051MR.U44 + HN091MR.NK5 má podle výkonové tabulky při A−15/W45 **4,85 kW** včetně vlivu odmrazování. Proti odhadu 4.68 kW zbývá jen **0.17 kW**. Jde o tabulkový maximální provoz, nikoli doložený tichý režim; skutečné podmínky instalace výkon ovlivňují. Jmenovitých 5,50 kW při A7/W35 není výkon pro návrhový mráz. Tepelné čerpadlo pro základní zjednodušený případ vychází těsně; nezbývá tím automaticky rezerva na souběžný ohřev TV. Soustava využívá prioritu TV a vestavěný elektrický dohřev, jejich provozní podíl však tato ustálená bilance nestanovuje.

## 6. Citlivost výsledku

Každý řádek mění jen uvedený předpoklad vůči hlavnímu případu; kombinovaný případ mění účinnost na 65 %, infiltraci na 0,20 h⁻¹, ΔU na 0,10 a λ izolací zvyšuje o 10 %. Nejde o pravděpodobnostní interval ani o vzájemně současně platné výsledky.

| Případ | Ztráta [kW] |
|---|---:|
| Suterén -15 °C | 4.68 |
| Suterén +0 °C | 4.40 |
| Suterén +5 °C | 4.30 |
| Suterén +10 °C | 4.21 |
| Boost 300 m³/h | 4.85 |
| Rekuperace pouze 65 % | 5.03 |
| Infiltrace 0,20 h⁻¹ | 5.19 |
| Tepelné mosty ΔU = 0,10 | 5.27 |
| Vodivosti izolací +10 % | 4.88 |
| Kombinovaný nepříznivý případ | 6.32 |
| Bez zpětného získávání tepla | 6.88 |

## 7. Rozsah použití a podklady

Výpočet poskytuje podklad pro rozhodnutí o vytápění a zpřesnění projektu. Nevyčísluje letní chladicí zátěž, roční spotřebu, samostatný bod bivalence ani normovou tepelnou ztrátu místností. Pro konečné potvrzení je třeba ověřit zejména těsnost stavby, tepelné mosty, provedení a návrhové U skladeb, venkovní dveře, zimní čistou účinnost větrání včetně rozvodů v suterénu, výkon FCU při přijatelném hluku a předávání tepla do místností bez těles. Změny rozměrů a skladeb vyžadují přepočet.

- [ASHRAE – princip ustálené zimní bilance a nevytápěné sousední prostory](https://handbook.ashrae.org/Handbooks/F21/SI/f21_ch17/F21_Ch17_si.aspx).
- [LG – tabulka výkonů R32 Split, strana 2](https://www.lg.com/content/dam/channel/wcms/hu/business/download/airsolution/2021_THERMA_V_%28AWHP%29_R32_Split_R410A_Split_leaflet_0302_FIN_20211102_223018918_.pdf).
- [IVAR – technický list SL DC, 03/2026](https://www.ivarcs.cz/storage/Folder_File/82001-84000/360054f7-d649-40dc-bfc5-9bfc64f13a35_file_cstl-ivar-sl-fancoil.pdf).
- Stavební část dokumentace: půdorysy, řezy a skladby konstrukcí; část VZT: normální průtok 240 m³/h a referenční účinnost HERU 77 %.
