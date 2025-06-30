# -*- coding: utf-8 -*-
from pydicom.datadict import tag_for_keyword

class DicomJsonProxy:
    """
    Lightweight accessor for DICOM JSON dictionaries emulating pydicom's Dataset API.
    """

    def __init__(self, dicom_json: dict):
        self._raw = dicom_json

    def __getattr__(self, tag_name):
        try:
            tag = tag_for_keyword(tag_name)
            return self._extract_value(self._raw[f"{tag.group:04X}{tag.element:04X}"])
        except KeyError:
            raise AttributeError(f"No such DICOM attribute: {name}")

    def __getitem__(self, tag):
        if tag in self._raw:
            return self._extract_value(self._raw[tag])
        raise KeyError(f"Tag {tag} not found in DICOM JSON.")

    def _extract_value(self, elem):
        if isinstance(elem, dict) and "Value" in elem and "vr" in elem:
            if elem['vr'] == 'SQ':
                return elem["Value"] # should be a list, check?
            # DICOM JSON format uses {"vr": "PN", "Value": ["..."]}, handle accordingly
            return elem["Value"][0] if isinstance(elem["Value"], list) else elem["Value"]
        return elem

    def get(self, name, default=None):
        try:
            return getattr(self, name)
        except AttributeError:
            return default
        