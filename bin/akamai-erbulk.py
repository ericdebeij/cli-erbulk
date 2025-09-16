"""Sample code: Create a datastream per productype for a group with all properties associated"""
import requests
import json
import sys
import csv
import copy
import hashlib
import pathlib
import argparse
import os

from akamai.edgegrid import EdgeGridAuth, EdgeRc
from urllib.parse import urljoin

from datetime import datetime, timezone
import time

def parse_iso8601(dt_str: str) -> datetime:
    """Parse ISO 8601 datetime string into a UTC datetime object."""
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception as e:
        print(f"Failed to parse date: {dt_str} ({e})")
        return None

def check_for_rate_limit(result):
    if result is not None:
        remaing = result.headers.get("X-RateLimit-Remaining")
        if remaing is not None and int(remaing) > 0:
            return

        waittill = result.headers.get("X-RateLimit-Next")
        if waittill is not None:
            dt = parse_iso8601(waittill)
            if dt is not None:
                now = datetime.now(timezone.utc)
                waitseconds = (dt - now).total_seconds()
                if waitseconds > 0:
                    print(f"Rate limit exceeded, waiting until {dt.isoformat()} ({waitseconds:.0f} seconds)")
                    time.sleep(waitseconds + 1)

class BulkRedirectManager:
    def __init__(self, edgerc="~/.edgerc", section="default", account = None):
        self._edgerc = edgerc
        self._section = section
        self._account = account
        self._config = EdgeRc(self._edgerc)
        self._session = requests.Session()
        self._session.auth = EdgeGridAuth.from_edgerc(self._config, section)
        self._baseurl = 'https://%s' % self._config.get(section, 'host')

    def akurl(self, p):
        """Helper function to build an Akamai API string"""
        x = urljoin(self._baseurl, p)
        if self._account:
            x = x + ("&" if "?" in x else "?") + "accountSwitchKey=" + self._account

        #print(x)
        return x

    def checkresponse(self, r):
        """Helper function to check the response of an API request"""      
        if r.status_code >= 300:
            print(f"Status code: {r.status_code}", file=sys.stderr)
            print(f"{r.request.method} {r.request.url}", file=sys.stderr)
            print(f"Response:", file=sys.stderr)
            print(r.text, file=sys.stderr)
            sys.exit(1)
            
    def listPolicies(self, ptype, prefix):
        """List policies using a specific prefix"""
        theset = {}

        result = self._session.get(self.akurl('/cloudlets/v3/policies'))
        self.checkresponse(result)

        policies = result.json()

        for p in policies["content"]:
            if p["cloudletType"] == ptype and p["name"].startswith(prefix):
                theset[p["name"]] = p
        return theset

    def createPolicy(self, policy):
        """Create a shared policy"""
        
        policyName = policy["name"]
        print(f"create policy {policyName}")
        result = self._session.post(self.akurl('/cloudlets/v3/policies'), 
            json=policy,
            headers={"content-type": "application/json"})

        self.checkresponse(result)

        return result.json()

    def listPolicyVersion(self, policyId):
        """List the policyversions for a shared policy"""

        result = self._session.get(self.akurl(f"/cloudlets/v3/policies/{policyId}/versions"), 
            headers={"content-type": "application/json"})

        self.checkresponse(result)

        return result.json()["content"]

    def createPolicyVersion(self, policyId, policyVersion):
        """Create a policyversion for a shared policy"""

        result = self._session.post(self.akurl(f"/cloudlets/v3/policies/{policyId}/versions"), 
            json=policyVersion,
            headers={"content-type": "application/json"})

        self.checkresponse(result)

        return result.json()

    def getPolicyVersion(self, policyId, policyVersion):
        """Get a policyversion for a shared policy"""

        result = self._session.get(self.akurl(f"/cloudlets/v3/policies/{policyId}/versions/{policyVersion}"), 
            headers={"content-type": "application/json"})

        self.checkresponse(result)

        return result.json()

    def er_bulkredirect(self, policyname, inputcsv, delimiter, hashnumber):
        versionset = []
        policyset = self.listPolicies("ER", policyname)

        #print(json.dumps(policyset, indent=2))

        if not policyname in policyset:
            print(f"basepolicy {policyname} has not been found, create shared policy {policyname} as a template for the bulk redirect policies")
            sys.exit()

        policyversions = self.listPolicyVersion(policyset[policyname]["id"])
        lastversionnr = 0
        for x in policyversions:
            if x["version"] > lastversionnr:
                lastversionnr = x["version"]

        basepolicy = self.getPolicyVersion(policyset[policyname]["id"], lastversionnr)

        br = dict(statusCode=301, type="erMatchRule", useIncomingQueryString=True, useRelativeUrl="relative_url")
        for i in range(0,hashnumber):
            hashpolicy = f"{policyname}_{i:03d}"
            if not hashpolicy in policyset:
                newpolicy = dict(cloudletType="ER", description=hashpolicy, name=hashpolicy, groupId=policyset[policyname]["groupId"])
                newpolicy["name"] = hashpolicy

                policyset[hashpolicy] = self.createPolicy(newpolicy)

            pv = dict(description="generated")

            mr = basepolicy["matchRules"].copy()
            
            count = len(mr)
            # We loop through the input file for every hash
            with open(inputcsv) as csvin:
                erreader = csv.reader(csvin, delimiter=delimiter)
                for row in erreader:
                    if len(row) < 2:
                        print(f"Row does not have 2 entries, is the delimiter ({delimiter}) used correctly in: {row}")
                        continue

                    # Take the first 4 hexadecimal character from the md5 has of the input path
                    result = hashlib.md5(bytes(row[0].lower(), 'utf-8'))
                    x = int(result.digest()[:2].hex(), 16) % hashnumber
                    
                    if x == i and row[0] != row[1]:
                        if row[0].startswith("/") and not row[0].startswith("//") and not "?" in row[0]:
                            r = br.copy()
                            r["matchURL"] = row[0]
                            r["redirectURL"] = row[1]
                            if row[1].startswith("//"):
                                row[1] = "https:" + row[1]
                            if not row[1].startswith("/"):
                                r["useRelativeUrl"] = "none"
                            if len(row) == 3:
                                if row[2] == "301" or row[2] == "302":
                                    r["statusCode"] = int(row[2])
                            count += 1
                            mr.append(r)
                        else:
                            print(f"Source {row[0]} not sanitised, utility cannot handle this (yet)", file=sys.stderr)

            pv["matchRules"] = mr
            print(f"create policyversion for {hashpolicy} with {count} rules")
            v = self.createPolicyVersion(policyset[hashpolicy]["id"], pv)
        
            versionset.append(dict(policyId=policyset[hashpolicy]["id"],version=v["version"]))

        return versionset

    def er_bulkactivate(self, versions, network, activate=True):
        operation = "ACTIVATION"
        if not activate:
            operation = "DEACTIVATION"
        result = None
        for v in versions:
            policyId = v["policyId"]
            b = dict(network=network.upper(), operation=operation, policyVersion=v["version"])
            while True:
                check_for_rate_limit(result)
                result = self._session.post(self.akurl(f"/cloudlets/v3/policies/{policyId}/activations"), 
                    json=b,
                    headers={"content-type": "application/json"})
                if result.status_code == 429:
                    continue
                break

            self.checkresponse(result)
            response = result.json()
            v[f"activation_{network}"] = response["id"]

        return versions

    def papi_search(self, propertyName):
        result = self._session.post(self.akurl('/papi/v1/search/find-by-value'),
            json=dict(propertyName=propertyName),
            headers={"content-type": "application/json", "PAPI-Use-Prefixes": "true"}
            )
        self.checkresponse(result)

        return result.json()

    def papi_getruletree(self, prop):
        propertyId = prop["propertyId"]
        propertyVersion = prop["propertyVersion"]
        contractId = prop["contractId"]
        groupId = prop["groupId"]
        result = self._session.get(self.akurl(f"/papi/v1/properties/{propertyId}/versions/{propertyVersion}/rules?contractId={contractId}&groupId={groupId}"),
            headers={"content-type": "application/json", "PAPI-Use-Prefixes": "true"}
            )
        self.checkresponse(result)

        return result.json()

    def papi_putruletree(self, prop, ruletree):
        propertyId = prop["propertyId"]
        propertyVersion = prop["propertyVersion"]
        contractId = prop["contractId"]
        groupId = prop["groupId"]
        result = self._session.put(self.akurl(f"/papi/v1/properties/{propertyId}/versions/{propertyVersion}/rules?contractId={contractId}&groupId={groupId}"),
            json=dict(rules=ruletree["rules"]),
            headers={"content-type": "application/json"}
            )

        self.checkresponse(result)

        return result.json()

    def er_pmrule(self, property, templatefile, policies, buckets):
        print(f"updating {property}")

        prop = self.papi_search(property)
        #print(json.dumps(prop, indent=2))

        v_staging = None
        v_production = None
        v_latest = None
        for pv in prop["versions"]["items"]:
            if pv["productionStatus"] == "ACTIVE":
                v_production = pv
            if pv["stagingStatus"] == "ACTIVE":
                v_staging = pv
            if pv["productionStatus"] == "INACTIVE" and pv["stagingStatus"] == "INACTIVE":
                v_latest = pv

        if v_latest is None:
            print("the latest version is not updatable, please create a version that can be updated")
            sys.exit(1)
        
        erbtpl = None
        with open(templatefile, 'r') as configfp:
            erbtpl = json.load(configfp)
        
        ruletree = self.papi_getruletree(v_latest)
        rulename = erbtpl["rule"]["name"]
        varname = erbtpl["variable"]["name"]
        
        idx = None
        i = 0
        if "variables" in ruletree["rules"]:
            for x in ruletree["rules"]["variables"]:
                if x["name"] == varname:
                    idx = i
                    break
                i += 1
        else:
            ruletree["rules"]["variables"] = []

        if idx is None:
            ruletree["rules"]["variables"].append(erbtpl["variable"])

        idx = None
        i = 0
        for x in ruletree["rules"]["children"]:
            if x["name"] == rulename:
                idx = i
                break
            i += 1

        if idx is None:
            print(f"the rule {rulename} is not found in the configuration, adding ruletree")
            idx = 0
            ruletree["rules"]["children"].insert(idx, erbtpl["rule"])

        template = ruletree["rules"]["children"][idx]["children"][0]
        #print(json.dumps(template, indent=2))
        c = []
        for i in range(len(policies)):
            p = policies[i]
            r = copy.deepcopy(template)
            r["name"] = f"Redirect {i:03d}"
            r["behaviors"][0]["options"]["cloudletSharedPolicy"] = policies[i]["policyId"]
            r["criteria"][0]["options"]["variableValues"] = [f"{i}"]
            c.append(r)

        ruletree["rules"]["children"][idx]["children"] = c
        ruletree["rules"]["children"][idx]["behaviors"][5]["options"]["operandOne"] = str(buckets)

        self.papi_putruletree(v_latest, ruletree)

        return 

#Setup a session authenticated with Akamai EdgeGrid
#edgerc = EdgeRc('~/api/hdebeij.edgerc')
#section = 'readwrite'
#baseurl = 'https://%s' % edgerc.get(section, 'host')
#sess = requests.Session()
#sess.auth = EdgeGridAuth.from_edgerc(edgerc, section)
#account = 'F-AC-2046772'

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk edge redirector")
    parser.add_argument("policy", help="basename of the policy")
    parser.add_argument("--parse", metavar="CSV", help="parse CSV and generate edge-redirect policies")
    parser.add_argument("--delimiter", metavar=",", help="CSV delimiter", default=",")
    parser.add_argument("--activate", nargs="+", help="push edge-redirect policies to STAGING and PRODUCTION", metavar="NETWORK", choices=["STAGING", "PRODUCTION"])
    parser.add_argument("--deactivate", nargs="+", help="push edge-redirect policies to STAGING and PRODUCTION", metavar="NETWORK", choices=["STAGING", "PRODUCTION"])
    
    parser.add_argument("--update-property", dest="properties", metavar="PROPERTY", nargs="+", help="properties to be updated (last version is used and should be editable)")
    parser.add_argument("--config", metavar="JSON", help="configuration file, defaults to ./POLICY.json")
    parser.add_argument("--buckets", metavar="N", type=int, help="number of buckets, defaults to number in the config or 32")

    parser.add_argument("--edgerc", help="edgerc config path passed to executed commands, defaults to ~/.edgerc", default="~/.edgerc")
    parser.add_argument("--section", help="edgerc section name passed to executed commands, defaults to 'default'", default="default")
    parser.add_argument("--account", help="account identification (only if multiple accounts can be used)")

    args = parser.parse_args()
    if args.config is None:
        args.config = f"{args.policy}.json"

    brm = BulkRedirectManager(edgerc=args.edgerc, section=args.section, account=args.account)

    if not args.parse and not args.activate and not args.properties and not args.deactivate:
        print("there is no action identified, please use either parse, activate, update-property or a combination", file=sys.stderr)
        sys.exit(1)

    configfileinfo = pathlib.Path(args.config)
    config = {}

    if configfileinfo.exists():
        with open(args.config, 'r') as configfp:
            config = json.load(configfp)
        if config["policyname"] != args.policy:
            print("configuration mismatch, policyname is different from the policyname in the configuration", file=sys.stderr)
            sys.exit(1)
        if args.buckets:
            config["buckets"] = args.buckets
    else:
        config["policyname"]= args.policy
        config["buckets"]=32 if args.buckets is None else args.buckets

    if not "template" in config:
        config["template"]=os.path.join(sys.path[0], "er_bulk_template.json")
    
    # Generate and upload the edgeredirect policies.
    if args.parse:
        config["policies"] = brm.er_bulkredirect(
            config["policyname"],
            args.parse, 
            args.delimiter,
            config["buckets"])
        config["inputfile"] = args.parse

        with open(args.config, 'w') as configfp:
            json.dump(config, configfp, indent=2)

    if args.activate:
        for network in args.activate:
            brm.er_bulkactivate(config["policies"], network)

    if args.deactivate:
        for network in args.deactivate:
            brm.er_bulkactivate(config["policies"], network, activate=False)


    if args.properties:
        for p in args.properties:
            brm.er_pmrule(p, config["template"], config["policies"], config["buckets"])



