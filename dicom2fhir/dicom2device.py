import uuid
import logging
from collections.abc import Iterable
from dicom2fhir.dicom_json_proxy import DicomJsonProxy
from fhir.resources.R4B.device import Device, DeviceDeviceName
from fhir.resources.R4B.annotation import Annotation
from fhir.resources.R4B.device import DeviceUdiCarrier

logger = logging.getLogger(__name__)

def _map_software_versions(ds: DicomJsonProxy) -> list[dict]:
    """
    Extract SoftwareVersions (DICOM 0018,1020) from the dataset and map to FHIR Device.version.
    
    This attribute is multi-valued (LO), so it returns a list of version strings.
    """
    # pydicom returns either a single value or a MultiValue object for VR LO
    if "SoftwareVersions" not in ds:
        return []
    
    # Normalize to list of strings
    raw = ds.SoftwareVersions
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
        return [{'value': str(item).strip()} for item in raw if item is not None]
    else:
        return [{'value': str(raw).strip()}]

def build_device_resource(ds: DicomJsonProxy, config: dict) -> Device:
    """
    Build FHIR Device resource from DICOM metadata (General Equipment Module).
    Extracts manufacturer, model, serial, version, institution, station, calibration, UDI, etc.
    """

    device = Device.model_construct()
    # Resource ID
    id_func = config.get("id_function", lambda t, d: str(uuid.uuid4()))
    device.id = id_func("Device", ds)

    # Identifiers
    identifiers = []

    if "DeviceSerialNumber" in ds:
        identifiers.append({
            "use": "official",
            "system": "urn:dicom:device-serial-number",
            "value": str(ds.DeviceSerialNumber)
        })

    if "DeviceUID" in ds:
        identifiers.append({
            "use": "official",
            "system": "urn:dicom:device-uid",
            "value": str(ds.DeviceUID)
        })

    if len(identifiers) > 0:
        device.identifier = identifiers

    # Manufacturer & Model
    if "Manufacturer" in ds:
        device.manufacturer = str(ds.Manufacturer)
    if "ManufacturerModelName" in ds:
        device.deviceName = [DeviceDeviceName.model_construct(name=str(ds.ManufacturerModelName), type="model-name")]

    # Software version(s)
    device.version = _map_software_versions(ds)

    # Institutional context
    if "InstitutionName" in ds:
        device.owner = {"display": str(ds.InstitutionName)}
    if "InstitutionalDepartmentName" in ds:
        device.location = {"display": str(ds.InstitutionalDepartmentName)}
    if "StationName" in ds:
        # Could be assigned to device.deviceName as 'station' or use part of location
        device.deviceName = device.deviceName or []
        device.deviceName.append(DeviceDeviceName.model_construct(name=str(ds.StationName), type="station-name"))

    # Physical/device-specific details
    try:
        if "SpatialResolution" in ds:
            device.property = device.property or []
            device.property.append({
                "type": {"text": "spatial-resolution-mm"},
                "valueQuantity": {"value": float(ds.SpatialResolution), "unit": "mm"}
            })
    except:
        logger.warning(f"Failed to extract SpatialResolution: {ds.SpatialResolution}")

    # Calibration date/time
    cal_date = str(ds.DateOfLastCalibration) if "DateOfLastCalibration" in ds else None
    cal_time = str(ds.TimeOfLastCalibration) if "TimeOfLastCalibration" in ds else None
    if cal_date or cal_time:
        dt = cal_date + (cal_time or "")
        device.note = device.note or []
        device.note.append(Annotation.model_construct(text=f"Last calibration: {dt}"))

    # Pixel padding—maybe not core but included
    if "PixelPaddingValue" in ds:
        device.note = device.note or []
        device.note.append(Annotation.model_construct(text=f"Pixel padding value: {ds.PixelPaddingValue}"))

    # UDI (Unique Device Identifier)
    if "UDISequence" in ds:
        udi_items = []
        for item in ds.UDISequence:
            if "UniqueDeviceIdentifier" in item:
                udi_items.append(DeviceUdiCarrier.model_construct(
                    deviceIdentifier=str(item.UniqueDeviceIdentifier))
                )
        if udi_items:
            device.udiCarrier = udi_items

    # Modality as device type
    if "Modality" in ds:
        device.type = {"text": str(ds.Modality)}

    return device