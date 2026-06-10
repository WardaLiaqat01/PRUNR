"""
Existence checks run against the target resource of each alerting sensor.

Each function has two clearly marked blocks:
  ① PRODUCTION — the real API/system call (commented out)
  ② TESTING    — mock data based on device name

To move to production: uncomment ① and remove ②.
"""
import socket
import subprocess
import platform
from concurrent.futures import ThreadPoolExecutor


# ─── Mock data ────────────────────────────────────────────────────────────────
# Mirrors what the five test sensors in mock_server/app.py would return from
# real AD, vCenter, and CMDB lookups.
#
#   dns/ping = False → host is actually gone from the network
#   ad/vcenter = False → no record found in directory / hypervisor
#   cmdb = "decommissioned" | "active" | "not_found"

MOCK_DEVICE_DATA: dict[str, dict] = {
    # Orphaned — decommissioned and unreachable
    "WEB-SERVER-01":  {"dns": False, "ping": False, "ad": False, "vcenter": False, "cmdb": "decommissioned"},
    "OLD-APP-SERVER": {"dns": False, "ping": False, "ad": False, "vcenter": False, "cmdb": "decommissioned"},
    # Broken connection — resource alive, monitoring link broken
    "FILE-SERVER-02": {"dns": True,  "ping": True,  "ad": True,  "vcenter": True,  "cmdb": "active"},
    "DB-SERVER-PROD": {"dns": True,  "ping": False, "ad": True,  "vcenter": True,  "cmdb": "active"},
    # Uncertain — reachable but not in AD/vCenter (network switch)
    "SWITCH-CORE-01": {"dns": True,  "ping": True,  "ad": False, "vcenter": False, "cmdb": "not_found"},
}


# ─── Check functions ──────────────────────────────────────────────────────────

def check_dns(host: str) -> bool:
    """Returns True if the hostname resolves in DNS."""
    # ① PRODUCTION: real DNS lookup — this works as-is, no changes needed
    try:
        socket.setdefaulttimeout(3)
        socket.gethostbyname(host)
        return True
    except (socket.gaierror, socket.timeout):
        return False


def check_ping(host: str) -> bool:
    """Returns True if the host responds to ICMP ping."""
    # ① PRODUCTION: real ping — this works as-is, no changes needed
    flag = "-n" if platform.system() == "Windows" else "-c"
    try:
        result = subprocess.run(
            ["ping", flag, "1", "-W", "2", host],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_ad(device_name: str) -> bool:
    """Returns True if a computer object exists in Active Directory.

    ① PRODUCTION — replace the mock return below with:

        from ldap3 import Server, Connection, NTLM, ALL
        server = Server(AD_HOST, get_info=ALL)
        conn = Connection(
            server, user=AD_BIND_USER, password=AD_BIND_PASS,
            authentication=NTLM, auto_bind=True
        )
        conn.search(
            search_base=AD_BASE_DN,
            search_filter=f"(&(objectClass=computer)(name={device_name}))",
            attributes=["name"]
        )
        return len(conn.entries) > 0
    """
    # ② TESTING
    return MOCK_DEVICE_DATA.get(device_name.upper(), {}).get("ad", False)


def check_vcenter_azure(device_name: str, host: str) -> bool:
    """Returns True if VM exists in vCenter or Azure.

    ① PRODUCTION (vCenter) — replace the mock return below with:

        from pyVmomi import vim
        from pyVim.connect import SmartConnect
        si = SmartConnect(host=VCENTER_HOST, user=VC_USER, pwd=VC_PASS, disableSslCertValidation=True)
        content = si.RetrieveContent()
        view = content.viewManager.CreateContainerView(
            content.rootFolder, [vim.VirtualMachine], True
        )
        return any(vm.name.upper() == device_name.upper() for vm in view.view)

    ① PRODUCTION (Azure) — replace the mock return below with:

        from azure.identity import DefaultAzureCredential
        from azure.mgmt.compute import ComputeManagementClient
        client = ComputeManagementClient(DefaultAzureCredential(), AZURE_SUBSCRIPTION_ID)
        vms = list(client.virtual_machines.list_all())
        return any(vm.name.upper() == device_name.upper() for vm in vms)
    """
    # ② TESTING
    return MOCK_DEVICE_DATA.get(device_name.upper(), {}).get("vcenter", False)


def check_cmdb(device_name: str) -> str:
    """Returns CMDB asset status: 'active' | 'decommissioned' | 'not_found'.

    ① PRODUCTION (ServiceNow) — replace the mock return below with:

        import httpx
        resp = httpx.get(
            f"{SNOW_URL}/api/now/table/cmdb_ci_computer",
            params={"sysparm_query": f"name={device_name}", "sysparm_fields": "install_status"},
            auth=(SNOW_USER, SNOW_PASS)
        )
        records = resp.json().get("result", [])
        if not records:
            return "not_found"
        # ServiceNow install_status: 1 = In Use, 7 = Retired
        return "active" if records[0]["install_status"] == "1" else "decommissioned"
    """
    # ② TESTING
    return MOCK_DEVICE_DATA.get(device_name.upper(), {}).get("cmdb", "not_found")


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def run_all_checks(device_name: str, host: str) -> dict:
    """Run DNS, ping, AD, and vCenter/Azure checks concurrently via thread pool."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        dns_f     = pool.submit(check_dns, host)
        ping_f    = pool.submit(check_ping, host)
        ad_f      = pool.submit(check_ad, device_name)
        vcenter_f = pool.submit(check_vcenter_azure, device_name, host)

    return {
        "dns_resolves":      dns_f.result(),
        "ping_responds":     ping_f.result(),
        "ad_object_exists":  ad_f.result(),
        "vcenter_vm_exists": vcenter_f.result(),
        "cmdb_status":       check_cmdb(device_name),   # Fast dict lookup, run sequentially
    }


# ─── Scoring ──────────────────────────────────────────────────────────────────

def score_evidence(evidence: dict) -> float:
    """
    Compute orphan confidence score (0–100).
    Higher score = stronger evidence that the resource is truly gone.

    Scoring rationale:
      DNS / ping failures alone are weak signals (could be firewall or maintenance).
      Missing AD object + missing VM record together are much stronger signals.
      CMDB 'decommissioned' is the strongest single signal.
    """
    score = 0
    if not evidence["dns_resolves"]:       score += 25
    if not evidence["ping_responds"]:      score += 15
    if not evidence["ad_object_exists"]:   score += 25
    if not evidence["vcenter_vm_exists"]:  score += 25
    if evidence["cmdb_status"] == "decommissioned": score += 35
    elif evidence["cmdb_status"] == "not_found":    score += 10
    return min(score, 100)


def classify_score(score: float) -> str:
    """
    Classify alert based on evidence score.

      >= 65 → orphan          (multiple systems confirm resource is gone)
      <= 30 → broken_connection (resource confirmed alive, monitoring link is broken)
      31-64 → uncertain       (conflicting evidence, could be either)
    """
    if score >= 65:
        return "orphan"
    elif score <= 30:
        return "broken_connection"
    return "uncertain"
