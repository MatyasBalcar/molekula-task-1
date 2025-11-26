import json
import re

from pypdf import PdfReader


class SPCExtractor:
    def __init__(self, raw_text):
        # normalizace textu
        self.text = re.sub(r'\s+', ' ', raw_text).strip()

    def _extract_section(self, current_section_id):
        """
        (interní)
        Extrahuje kapitolu (třeba 4.3 kde jsou alergie nbeo 4.2 kde je věk), zastaví se u další kapitoly
        :param current_section_id: id kapitoly, eg: 4.2, 4.3
        :return: kapitolu (str)
        """

        # "malá" a "velká" kapitola
        parts = current_section_id.split('.')
        if len(parts) == 2:
            next_minor = int(parts[1]) + 1
            next_section_id = f"{parts[0]}.{next_minor}"
        else:
            next_section_id = r"4\.\d"

        pattern = rf"{re.escape(current_section_id)}.*?(?=\s+{re.escape(next_section_id)}|$)"

        match = re.search(pattern, self.text, re.IGNORECASE)
        return match.group(0) if match else ""

    def analyze_age_restriction(self):
        """
        Získá kapitolu 4.2 (věk), pomocí keywords zkusí najít hranici
        :return: info o věku (json)
        """
        section_text = self._extract_section("4.2")
        result = {
            "category": "min_age",
            "value": None,
            "status": "UNKNOWN",
            "evidence": ""
        }

        if not section_text:
            return result

        age_patterns = [
            r"do\s+(\d+)\s+let",
            r"mladší\s+(\d+)\s+let",
            r"mladších\s+(\d+)\s+let",
            r"pod\s+(\d+)\s+let"
        ]

        for pattern in age_patterns:
            match = re.search(pattern, section_text, re.IGNORECASE)
            if match:
                result["value"] = int(match.group(1))
                result["status"] = "RESTRICTED"
                result["evidence"] = match.group(0)
                return result
        # fallback na pediatrick, možná přidat i další?
        if "pediatrick" in section_text.lower() and \
                any(x in section_text.lower() for x in ["nebyla stanovena", "nejsou údaje", "nedoporučuje"]):
            result["status"] = "NOT_RECOMMENDED_PEDIATRIC"
            result["evidence"] = "Nalezena zmínka o omezení pro pediatrickou populaci bez konkrétního čísla."

        return result

    def analyze_allergies_and_refs(self):
        """
        Podobné jak alergie, akorát 4.3
        Taky hledá reference na body kam se podívat
        :return: info o alergiích (json)
        """
        section_text = self._extract_section("4.3")
        findings = []

        if not section_text:
            return findings

        # časté slova u alergií
        allergy_pattern = r"((?:Hypersenzitivita|Přecitlivělost|Alergie).*?)(?=\s+-\s|\s+•\s|\s+pacienti|\s+stavy|\s*$)"
        match_allergy = re.search(allergy_pattern, section_text, re.IGNORECASE)

        if match_allergy:
            raw_text = match_allergy.group(1)
            clean_text = re.sub(r"(?:Hypersenzitivita|Přecitlivělost|Alergie)(?:\s+na)?\s*", "", raw_text,
                                flags=re.IGNORECASE)
            parts = re.split(r",|\snebo\s", clean_text)
            for p in parts:
                cleaned_item = p.strip().strip('.;')
                if len(cleaned_item) > 2:
                    findings.append({"type": "ALLERGY_TEXT", "value": cleaned_item})

        # Kontrola referencí
        ref_pattern = r"(?:bod[a-ž]*|část[a-ž]*|viz)\s+(\d+\.\d+)"
        references = re.findall(ref_pattern, section_text, re.IGNORECASE)

        for ref in set(references):
            findings.append({
                "type": "SECTION_REFERENCE",
                "value": ref,
                "note": f"Nutno zkontrolovat sekci {ref}."
            })

        return findings


def parse(path):
    """
    POarsne pdf podle pathy
    :param path: path na pdf
    :return: text pdfka (str)
    """
    reader = PdfReader(path)

    pages = reader.pages
    text = ""

    for page in pages:
        text += page.extract_text()

    return text


extractor = SPCExtractor(parse("priloha_dlp-2.pdf"))

age_result = extractor.analyze_age_restriction()
allergy_result = extractor.analyze_allergies_and_refs()

final_output = {
    "drug_name": "Buprenorfin Viatris",
    "analysis": {
        "age_restriction": age_result,
        "contraindications_findings": allergy_result
    }
}

print(json.dumps(final_output, indent=4, ensure_ascii=False))
