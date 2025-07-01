# -*- coding: utf-8 -*-
import os
import uuid
import hashlib
from typing import Callable
from dicom2fhir.dicom_json_proxy import DicomJsonProxy

def get_or(d: dict, path: str, default=None):
    """
    Get a value from a nested dictionary using a dot-separated path.
    If the path does not exist, return the default value.
    """
    keys = path.split('.')
    val = d
    for key in keys:
        if isinstance(val, dict) and key in val:
            val = val[key]
        else:
            return default
    return val if val is not None else default

def env_or_config(env: str, config_path: str, config: dict):
    """
    Return the value of an environment variable or a configuration key.
    If neither is set raise a ValueError.
    """
    if env in os.environ:
        return os.environ[env]

    val = get_or(config, config_path)
    if val is None:
        raise ValueError(f"Neither environment variable '{env}' nor configuration key '{config_path}' is set.")
    return val

# default id functions
def default_id_function(pepper: str | None = None) -> Callable[[str, DicomJsonProxy], str]:
    """
    Default ID function for FHIR resource id generation.
    Can be customized with a pepper string for additional uniqueness.
    """
    def _id(resource_type: str, ds: DicomJsonProxy, extra: str|None = "") -> str:
        if not isinstance(ds, DicomJsonProxy):
            raise TypeError("Expected a DicomJsonProxy object")

        base_string = extra
        if resource_type == "ImagingStudy" and "StudyInstanceUID" in ds:
            base_string = f"{base_string}{ds.StudyInstanceUID}"
        elif resource_type == "Patient" and "PatientID" in ds:
            base_string = f"{base_string}{ds.PatientID}"
        elif resource_type == "Device" and "DeviceSerialNumber" in ds:
            uid = ds.get("DeviceUID") or ''
            ser = ds.get("DeviceSerialNumber") or ''
            mod = ds.get("ManufacturerModelName") or ''
            base_string = f"{base_string}{uid}{ser}{mod}"
        elif resource_type == "Observation":
            uid = ds.StudyInstanceUID if ds.non_empty("StudyInstanceUID") else ""
            study_date = ds.StudyDate if ds.non_empty("StudyDate") else ""
            study_time = ds.StudyTime if ds.non_empty("StudyTime") else ""
            base_string = f"{base_string}{uid}{study_date}{study_time}"
        else:
            return str(uuid.uuid4())

        return hashlib.sha256(f"{base_string}{pepper or ''}".encode("utf-8")).hexdigest()

    return _id