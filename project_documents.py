"""Stable document numbers and output paths for the new house project."""

from dataclasses import dataclass
from pathlib import Path


PROJECT_DIR = Path("projekt2")
ARCHITECTURE = "D.1.1. Architektonicko-stavební řešení"
STRUCTURE = "D.2. Základní stavebně konstrukční řešení"
SITUATION = "C. Situační výkresy"
SERVICES = "D.1.2. Technologické řešení"
ZTI = f"{SERVICES}/ZTI. Zdravotně technické instalace"
ELE = f"{SERVICES}/ELE. Elektroinstalace"
VZT = f"{SERVICES}/VZT. Vzduchotechnika"
VYT = f"{SERVICES}/VYT. Vytápění a chlazení"

# Retain the former paths to support migration and trace old drawing references.
_OLD_ARCH = "D1.1. Architektonicko Stavební Řešení"
_OLD_ZTI = "D1.5. Zdravotechnické Instalace"
_OLD_ELE = "D1.4. Zařízení Silnoproudé Elektrotechniky"
_OLD_VZT = "D1.6. Řízené Větrání"
_OLD_VYT = "D1.7. Vytápění"
_OLD_SITE = "C. Situace Stavby"


@dataclass(frozen=True)
class ProjectDrawing:
    key: str
    number: str
    title: str
    folder: str
    legacy_pdf: str

    @property
    def filename(self):
        return f"{self.number}. {self.title}.pdf"

    def pdf(self, project=PROJECT_DIR):
        return Path(project) / self.folder / self.filename

    def svg(self, project=PROJECT_DIR):
        return self.pdf(project).parent / "src" / self.pdf(project).with_suffix(".svg").name

    def working_svg(self, project=PROJECT_DIR):
        return Path(project) / f"{self.key}.svg"


_ROWS = (
    ProjectDrawing("basement", "D.1.1.2-01", "Půdorys 1.PP", ARCHITECTURE, f"{_OLD_ARCH}/D1.1.9. Půdorys suterénu.pdf"),
    ProjectDrawing("ground", "D.1.1.2-02", "Půdorys 1.NP", ARCHITECTURE, f"{_OLD_ARCH}/D1.1.1. Půdorys 1.NP.pdf"),
    ProjectDrawing("upper", "D.1.1.2-03", "Půdorys 2.NP – podkroví", ARCHITECTURE, f"{_OLD_ARCH}/D1.1.3. Půdorys podkroví.pdf"),
    ProjectDrawing("aa", "D.1.1.2-04", "Řez A–A", ARCHITECTURE, f"{_OLD_ARCH}/D1.1.11. Řez AA.pdf"),
    ProjectDrawing("bb", "D.1.1.2-05", "Řez B–B", ARCHITECTURE, f"{_OLD_ARCH}/D1.1.12. Řez BB.pdf"),
    ProjectDrawing("cc", "D.1.1.2-06", "Řez C–C", ARCHITECTURE, f"{_OLD_ARCH}/D1.1.16. Řez CC.pdf"),
    ProjectDrawing("pohledy", "D.1.1.2-07", "Pohledy", ARCHITECTURE, f"{_OLD_ARCH}/D1.1.5. Pohledy.pdf"),
    ProjectDrawing("sousede", "D.1.1.2-08", "Začlenění stavby do okolní zástavby", ARCHITECTURE, f"{_OLD_ARCH}/D1.1.18. Porovnání se sousední zástavbou.pdf"),
    ProjectDrawing("found", "D.2.3-01", "Základy – půdorys a řez Z–Z", STRUCTURE, f"{_OLD_ARCH}/D1.1.10. Základy.pdf"),
    ProjectDrawing("basement_ceiling", "D.2.3-02", "Strop nad 1.PP", STRUCTURE, f"{_OLD_ARCH}/D1.1.13. Strop nad suterénem.pdf"),
    ProjectDrawing("basement_ceiling2", "D.2.3-03", "Strop nad 1.PP – kladečský plán MIAKO", STRUCTURE, f"{_OLD_ARCH}/D1.1.14. Strop nad suterénem - podrobný plán.pdf"),
    ProjectDrawing("ceiling", "D.2.3-04", "Strop nad 1.NP", STRUCTURE, f"{_OLD_ARCH}/D1.1.2. Strop nad 1.NP.pdf"),
    ProjectDrawing("ceiling2", "D.2.3-05", "Strop nad 1.NP – kladečský plán MIAKO", STRUCTURE, f"{_OLD_ARCH}/D1.1.15. Strop nad 1.NP - podrobný plán.pdf"),
    ProjectDrawing("roof", "D.2.3-06", "Krov", STRUCTURE, f"{_OLD_ARCH}/D1.1.4. Krov.pdf"),
    ProjectDrawing("kanal_basement", "D.1.2.2-ZTI-01", "Kanalizace – půdorys 1.PP", ZTI, f"{_OLD_ZTI}/D1.5.1. Kanalizace - Půdorys suterénu.pdf"),
    ProjectDrawing("kanal_ground", "D.1.2.2-ZTI-02", "Kanalizace – půdorys 1.NP", ZTI, f"{_OLD_ZTI}/D1.5.2. Kanalizace - Půdorys 1.NP.pdf"),
    ProjectDrawing("kanal_upper", "D.1.2.2-ZTI-03", "Kanalizace – půdorys 2.NP", ZTI, f"{_OLD_ZTI}/D1.5.3. Kanalizace - Půdorys podkroví.pdf"),
    ProjectDrawing("kanal", "D.1.2.2-ZTI-04", "Kanalizace – rozvinuté schéma", ZTI, f"{_OLD_ZTI}/D1.5.4. Kanalizace.pdf"),
    ProjectDrawing("voda_basement", "D.1.2.2-ZTI-05", "Vodovod – půdorys 1.PP", ZTI, f"{_OLD_ZTI}/D1.5.7. Vodovod - Půdorys suterénu.pdf"),
    ProjectDrawing("voda_ground", "D.1.2.2-ZTI-06", "Vodovod – půdorys 1.NP", ZTI, f"{_OLD_ZTI}/D1.5.5. Vodovod - Půdorys 1.NP.pdf"),
    ProjectDrawing("voda_upper", "D.1.2.2-ZTI-07", "Vodovod – půdorys 2.NP", ZTI, f"{_OLD_ZTI}/D1.5.6. Vodovod - Půdorys podkroví.pdf"),
    ProjectDrawing("elektro_basement", "D.1.2.2-ELE-01", "Elektroinstalace – půdorys 1.PP", ELE, f"{_OLD_ELE}/D1.4.3. Elektro - Půdorys suterénu.pdf"),
    ProjectDrawing("elektro_ground", "D.1.2.2-ELE-02", "Elektroinstalace – půdorys 1.NP", ELE, f"{_OLD_ELE}/D1.4.1. Elektro - Půdorys 1.NP.pdf"),
    ProjectDrawing("elektro_upper", "D.1.2.2-ELE-03", "Elektroinstalace – půdorys 2.NP", ELE, f"{_OLD_ELE}/D1.4.2. Elektro - Půdorys podkroví.pdf"),
    ProjectDrawing("rozvadec", "D.1.2.2-ELE-04", "Rozvaděč – jednopólové schéma", ELE, f"{_OLD_ELE}/D1.4.4. Rozvaděč - jednopólové schéma.pdf"),
    ProjectDrawing("vetrani_ground", "D.1.2.2-VZT-01", "Řízené větrání – půdorys 1.NP", VZT, f"{_OLD_VZT}/D1.6.1. Řízené větrání - Půdorys 1.NP.pdf"),
    ProjectDrawing("vetrani_upper", "D.1.2.2-VZT-02", "Řízené větrání – půdorys 2.NP", VZT, f"{_OLD_VZT}/D1.6.2. Řízené větrání - Půdorys podkroví.pdf"),
    ProjectDrawing("vetrani_basement", "D.1.2.2-VZT-03", "Řízené větrání – půdorys 1.PP", VZT, f"{_OLD_VZT}/D1.6.3. Řízené větrání - Půdorys suterénu.pdf"),
    ProjectDrawing("vytapeni_ground", "D.1.2.2-VYT-01", "Vytápění a chlazení – půdorys 1.NP", VYT, f"{_OLD_VYT}/D1.7.1. Vytápění - Půdorys 1.NP.pdf"),
    ProjectDrawing("vytapeni_upper", "D.1.2.2-VYT-02", "Vytápění a chlazení – půdorys 2.NP", VYT, f"{_OLD_VYT}/D1.7.2. Vytápění - Půdorys podkroví.pdf"),
    ProjectDrawing("situace_prehled", "C.1-C.2", "Přehledová a katastrální situace", SITUATION, f"{_OLD_SITE}/C1.1. Přehledová a katastrální mapa.pdf"),
    ProjectDrawing("situace", "C.3", "Koordinační situační výkres", SITUATION, f"{_OLD_SITE}/C1.2. Koordinační Situace.pdf"),
    ProjectDrawing("zastineni", "C.4-01", "Posouzení odstupového úhlu stínění", SITUATION, f"{_OLD_ARCH}/D1.1.17. Zastínění sousedního RD.pdf"),
)
DRAWINGS = {item.key: item for item in _ROWS}


def document_path(key, project=PROJECT_DIR):
    return DRAWINGS[key].pdf(project)


def expand_drawing_targets(arguments):
    """Expand the case-sensitive C shortcut to the situation drawings."""
    situation_targets = tuple(key for key, drawing in DRAWINGS.items() if drawing.folder == SITUATION)
    return list(dict.fromkeys(
        target
        for argument in arguments
        for target in (situation_targets if argument == "C" else (argument,))
    ))
