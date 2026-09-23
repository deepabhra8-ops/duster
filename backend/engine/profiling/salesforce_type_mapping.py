"""
Type mapping utility for resolving source datatypes to target SQL datatypes.
Provides lightweight string representations for the profiling map.
"""


def map_salesforce_type(sf_type: str) -> str:
    """
    Map Salesforce's native metadata field types to standard SQL datatype strings.
    Based on PostgreSQL/Standard SQL types for broad compatibility.
    """
    if not sf_type:
        return "VARCHAR(65535)"

    sf_type = sf_type.lower().strip()

    if sf_type in ['id', 'reference']:
        return "VARCHAR(255)"
    if sf_type in ['boolean', 'checkbox']:
        return "Boolean"
    if sf_type in ['currency', 'double', 'percent', 'number']:
        return "Float"
    if sf_type in ['int', 'autonumber', 'rollup summary']:
        return "BigInteger"
    if sf_type == 'date':
        return "Date"
    if sf_type == 'datetime':
        return "DateTime"
    if sf_type == 'time':
        return "Time"
    if sf_type in ['email', 'phone', 'string', 'picklist', 'multipicklist', 'formula', 'text', 'encryptedstring']:
        return "VARCHAR(255)"
    if sf_type == 'url':
        return "VARCHAR(2048)"
    if sf_type in ['textarea', 'longtextarea', 'richtextarea', 'location', 'address', 'anytype', 'complexvalue']:
        return "VARCHAR(65535)"

    return "Text"


