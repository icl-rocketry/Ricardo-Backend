# This code takes a HTML downloaded from app.diagrams.net and makes every group a button.

# First we need to extract the underlying graph representation from the HTML.
#   It is stored as a base64 encoded string of a zlib compressed xml file.
#   The zlib compression doesn't have any header information, so that makes things annoying.

# Secondly we get all the groups, and add tags to make them clickable links in the viewer.
#   Each group needs to have a text element with a unique name, so we can uniquely identify each click (TODO: figure out what link to give em)
# Code to decompress the nonsense data

from bs4 import BeautifulSoup
import json
import xml.etree.ElementTree as ET
import zlib, base64
import urllib.parse
import argparse

def decode_diagram(raw: str) -> ET.Element:
    dec = zlib.decompressobj(-zlib.MAX_WBITS)
    decoded = base64.b64decode(raw)
    decompressed = dec.decompress(decoded)
    raw_xml = urllib.parse.unquote(decompressed)
    return ET.fromstring(raw_xml)

# Note this isn't an exact inverse of decode, but works well enough
# encode(decode(data)) != data, but would still contain the same data
# I've compressed it more than drawio 
def encode_diagram(diagram: ET.Element) -> str:
    enc = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS, zlib.DEF_MEM_LEVEL, 0)
    
    stringified = ET.tostring(diagram, encoding='utf-8')
    quoted = urllib.parse.quote(stringified)
    compressed = enc.compress(quoted.encode('utf-8'))
    compressed += enc.flush()
    return base64.b64encode(compressed).decode('utf-8')

# The html file has the diagram text buried in config
# This code digs it out
def get_diagram_from_html(filename: str) -> str:
    with open(filename, "r") as file:
        soup = BeautifulSoup(file, "html.parser")
        diagram_div = soup.find_all("div")[0] # Diagram info is in the first div
        diagram_obj = diagram_div.get("data-mxgraph")
        diagram_xml = json.loads(diagram_obj)["xml"] # Get the surrounding xml
        xml = ET.fromstring(diagram_xml)
        return xml.find("diagram").text

def insert_into_template(template_file: str, new_filename: str, diagram: ET.Element) -> None:
    with open(template_file, "r") as file:
        data = file.read().replace("$TEMPLATE", encode_diagram(diagram))
    
    with open(new_filename, "w") as file:
        file.write(data)


def add_links_to_groups(diagram: ET.Element) -> None:
    root = diagram.find("root")
    for child in list(root):
        # For each group, add a <UserObject> element around it with the link
        style = child.get("style")
        
        if style is None or "group" not in style:
            continue

        root.remove(child)
        attrs = child.attrib

        user_object = ET.SubElement(root, "UserObject", attrib={"label": "", "link": "Request:\{\"hello\":1\}", "id": attrs["id"]})

        del attrs["id"] # Id is already in the UserObject
        mx_cell = ET.SubElement(user_object, "mxCell", attrib=attrs)

        for subchild in list(child):
            child.remove(subchild)
            mx_cell.append(subchild)

# Returns a list of ids which have animations defined
def get_animation_ids(diagram: ET.Element):
    anim_ids = []

    root = diagram.find("root")
    for child in list(root):
        rule = child.get("rule")
        if rule is None:
            continue
        
        events = child.get("events")
        if events is None:
            events = ""

        events = events.split(",")
        _id = child.get("id")
        
        anim_ids.append((_id, rule, events))
    
    return anim_ids

def parse_rules(filename: str, template_filename: str):
    with open(template_filename) as file:
        template = json.load(file)

    with open(filename) as file:
        rules = json.load(file)

    rules_dict = dict()

    for rule in rules:
        generated_rule = template.copy()

        name = rule["name"]
        if name in rules_dict:
            raise Exception(f"Duplicate rule {name}")

        generated_rule["alias"] = name
        generated_rule["column"] = rule["data_source"]
        generated_rule["invert"] = not rule["thresholds"]["ascending"]
        
        thresholds = []
        colours = []
        for pair in rule["thresholds"]["values"]:
            value = pair["value"] 
            if value != "base":
                thresholds.append(value)
            colours.append(pair["colour"])
        
        generated_rule["colors"] = colours
        generated_rule["thresholds"] = thresholds
        
        events = []
        base_event = {"hidden": False, "pattern": ""}
        for event in rule["events"]:
            events.append(base_event | event) # Only works in python 3.9+
        generated_rule["eventData"] = events
        
        rules_dict[name] = generated_rule
    return rules_dict

def expand_rules(rules, diagram):
    for (id, rule_name, events) in get_animation_ids(diagram):
        if rule_name not in rules:
            raise Exception(f"Rule {rule_name} not found in rules.json")
        
        rule = rules[rule_name]

        newEventData = [] # This is disgusting
        for event in events:
            if event == "colour":
                shapeData = {
                    "colorOn": "a",
                    "hidden": False,
                    "pattern": id,
                    "style": "fillColor"
                }
                rule["shapeData"].append(shapeData)
            
            eventCfg = [ev.copy() for ev in rule["eventData"] if ev["style"] == event][0]
            eventCfg["pattern"] = id
            newEventData.append(eventCfg)
        
        rule["eventData"] = newEventData
        rules[rule_name] = rule
    return rules

if __name__ == "__main__":
    raw = get_diagram_from_html("propped.html")
    diagram = decode_diagram(raw)

    add_links_to_groups(diagram)
    
    rules = parse_rules("rules.json", "rule_template.json")

    rules_data = expand_rules(rules, diagram)

    with open("dashboard_template.json") as file:
        dashboard_template = json.load(file)

    for panel in dashboard_template["panels"]:
        if "flowchartsData" in panel:
            panel["flowchartsData"]["flowcharts"][0]["xml"] = raw
            panel["rulesData"]["rulesData"] = rules_data
            break

    with open("out.json", "w") as file:
        json.dump(dashboard_template, file)