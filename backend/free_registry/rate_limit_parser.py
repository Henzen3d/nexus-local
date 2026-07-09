import re

def _normalize_k(s: str) -> int:
    """'500K' -> 500000, '1,000,000' -> 1000000"""
    s = s.replace(',', '').upper().strip()
    if s.endswith('K'):
        return int(float(s[:-1]) * 1000)
    elif s.endswith('M'):
        return int(float(s[:-1]) * 1000000)
    elif s.endswith('B'):
        return int(float(s[:-1]) * 1000000000)
    return int(s)

def parse_rate_limit(raw: str) -> dict:
    """
    Realiza o parsing de strings de limites de taxa.
    Retorna um dicionário contendo rpm, rpd, tpm, tpd, rps, ou tpm_month.
    Se não for possível parsear, define parse_confidence como 'unparseable'.
    """
    if not raw:
        return {"parse_confidence": "unparseable", "raw": raw}
        
    result = {}

    rpm_match = re.search(r'([\d,]+K?)\s*RPM', raw, re.IGNORECASE)
    rpd_match = re.search(r'([\d,]+K?)\s*RPD', raw, re.IGNORECASE)
    tpm_match = re.search(r'([\d,]+K?)\s*(?:tokens/minute|TPM)', raw, re.IGNORECASE)
    tpd_match = re.search(r'([\d,]+K?)\s*(?:tokens/day|TPD)', raw, re.IGNORECASE)
    tpm_month_match = re.search(r'([\d,]+K?)\s*(?:tokens/month)', raw, re.IGNORECASE)
    rps_match = re.search(r'([\d,]+K?)\s*(?:RPS|requests?/second)', raw, re.IGNORECASE)
    rph_match = re.search(r'([\d,]+K?)\s*(?:req/hr|requests?/hour)', raw, re.IGNORECASE)

    if rpm_match: result['rpm'] = _normalize_k(rpm_match.group(1))
    if rpd_match: result['rpd'] = _normalize_k(rpd_match.group(1))
    if tpm_match: result['tpm'] = _normalize_k(tpm_match.group(1))
    if tpd_match: result['tpd'] = _normalize_k(tpd_match.group(1))
    if tpm_month_match: result['tpm_month'] = _normalize_k(tpm_month_match.group(1))
    if rps_match: result['rps'] = _normalize_k(rps_match.group(1))
    
    if rph_match:
        rph = _normalize_k(rph_match.group(1))
        result['rpd'] = rph * 24
        result['rpm'] = max(1, rph // 60)

    if not result:
        return {"parse_confidence": "unparseable", "raw": raw}

    result["parse_confidence"] = "high"
    return result
