import re
import os
import yaml
from collections import defaultdict, Counter
import logging
import pandas as pd
from copy import deepcopy
import pprint
import math
from itertools import chain


PROJECT_NAME = "Ontologise"
DEFAULT_SETTINGS = "settings.yaml"

data_point_separator = "\\t"

### Regexes to identify specific lines
empty_line_regex = r"^\s+$"
ignore_line_regex = r"^!.*$"
header_line_regex = r"^##\w+:"
content_line_regex = r"^###\t"
shortcut_line_regex = r"^###\t\^\d+:$"
shortcut_definition_regex = r"^###\t[^\*\[\]\{\}]+\*?$"
peopla_line_regex = r"^###\t(>\t)*@?\[.*\](\(.*\))?(\{.*\})?$"
peopla_regex = r"^(\@)?(w\/)?\[(.*?)\](\(.*\))?(\{.*\})?(\*)?$"
peopla_attribute_regex = r"^###\t\t[^\*]+\*?$"
peopla_pedigree_attribute_regex = r"^###\t(>\t)+[^\*\[]+\*?$"
peopla_embedded_attribute_regex = r"^###\t([>\t]+)[^\*\[](.*)$"
peopla_relation_line_regex = r"^###\t(>\t)+\*(.*)\*$"
peopla_relation_depth_regex = r">\t"
peopla_relation_string_regex = r"\*(.*)\*"
peopla_relation_target_regex = r"^###\t(>\t)+@?\[.*\](\(.*\))?(\{.*\})?$"
peopla_relation_scope_regex = r"^###\t(>).*$"

action_regex = r"^([^\*]+)(\*)?$"
action_attribute_regex = r"^###\t\t\t[^\*]+\*?$"
pedigree_action_attribute_regex = r"^###\t[\t<]+(\t)+[^\*]+\*?$"
action_group_regex = r"^###\t(>\t)*(vs|w/).*$"
action_group_vs_regex = r"^###\t(>\t)*vs\[.*$"
action_group_w_regex = r"^###\t(>\t)*w\/\[.*$"

action_scope_regex = r"^###\t(\S*)\t.*$"
data_table_header_regex = rf"^###{re.escape(data_point_separator)}.*$"
data_table_linebreak_regex = r"^\[/\]$"
data_table_global_id_regex = r"^###\t\{.*\}$"
data_table_local_id_regex = r"^###\t\(.*\)$"
data_table_end_regex = rf"^###{re.escape(data_point_separator)}END$"

human_annotations_to_remove_rg = [r"\s*\[<-\]"]

# Obtained from: https://stackoverflow.com/questions/384076/how-can-i-color-python-logging-output
# Colour codes from: https://gist.github.com/abritinthebay/d80eb99b2726c83feb0d97eab95206c4
# Bold text: https://stackoverflow.com/questions/50460222/bold-formatting-in-python-console
class CustomFormatter(logging.Formatter):

    grey = "\x1b[38;20m"
    cyan = "\x1b[46m"
    magenta = "\x1b[45m"
    bold_red = "\x1b[41m"
    reset = "\x1b[0m"
    # format = "\033[1m [%(name)s][%(levelname)-5s][%(funcName)s][%(filename)s] \033[0m \n%(message)s"
    debug_format = (
        "\033[1m🪲 [%(filename)s::%(funcName)s::%(lineno)d]\033[0m\n%(message)s"
    )
    info_format = "\033[1m%(message)s"
    format = "\033[1m%(message)s"

    FORMATS = {
        logging.DEBUG: cyan + debug_format + reset,
        logging.INFO: grey + info_format + reset,
        logging.WARNING: magenta + format + reset,
        logging.ERROR: bold_red + format + reset,
        logging.CRITICAL: bold_red + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


logger = logging.getLogger(PROJECT_NAME.upper())
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(CustomFormatter())

logger.addHandler(ch)

# set up pretty printer
# https://stackoverflow.com/questions/77991049/is-there-a-way-to-print-a-formatted-dictionary-to-a-python-log-file
pp = pprint.PrettyPrinter(indent=2, sort_dicts=False)


def log_pretty(obj):
    pretty_out = f"{pp.pformat(obj)}"
    return f"{pretty_out}\n"


def read_settings_file(file):
    settings = ""

    with open(file) as stream:
        try:
            settings = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logger.error(exc)

    return settings


def flatten_dict(nested_dict):
    res = {}
    if isinstance(nested_dict, dict):
        for k in nested_dict:
            flattened_dict = flatten_dict(nested_dict[k])
            for key, val in flattened_dict.items():
                key = list(key)
                key.insert(0, k)
                res[tuple(key)] = val
    else:
        res[()] = nested_dict
    return res


class DataTable:
    def __init__(self, fields, shortcuts):
        self.column_names = fields
        self.column_num = len(fields)
        self.attributes = shortcuts

        logger.info("Creating a table")
        logger.debug(f" - {self.column_num} columns")
        logger.debug(f" - Column names: {','.join(self.column_names)}")
        logger.debug(f" - Attributes are: {self.attributes}")

    def __str__(self):
        out_s = f"{self.column_num} columns"
        if self.attributes:
            shortcut_list = ", ".join(self.attributes.keys())
            out_s += f" (+{shortcut_list} by shortcut)"
        return( out_s )

class DataPoint:
    def __init__(self, list, table):

        logger.info("Creating a datapoint")
        logger.debug(f" - data point list provided [{list}]")
        logger.debug(f" - needs to fit into [{table.column_num}] slots")

        if len(list) < table.column_num:
            list += [""] * (table.column_num - len(list))
        elif len(list) > table.column_num:
            list = list[: table.column_num]

        logger.debug(f" - list doctored to [{list}]")

        data = deepcopy(table.attributes)

        for (key, val) in zip(table.column_names, list):
            if ":" in key:
                (key, subkey) = key.split(":")
                data[key][subkey] = val
            else:
                data[key] = val

        self.cells = data
        self.global_id = None
        self.local_id = None

    def add_global_id(self, id):
        self.global_id = id

    def add_local_id(self, id):
        self.local_id = id


class ActionGroup:
    """
    A ActionGroup involves two or more Peoplas
    """

    def __init__(
        self, type, directed=False, source_peopla=None, target_peoplas=[], attributes={}
    ):

        self.type = type
        self.directed = directed
        self.source_peopla = source_peopla
        self.target_peoplas = target_peoplas

        ### Aggributes of the Relationship itself
        self.attributes = attributes

        ### Keeping track of attribute instances
        self.attribute_instances = {}

        ### Evidence reference (line number from original file)
        self.evidence_reference = []

    def __str__(self):
        out_s = (
            f"{'directed' if self.directed else 'undirected'} {self.type} ActionGroup\n"
        )
        out_s = out_s + f"...involving the following source Peoplas:\n"

        for n, peopla in enumerate([self.source_peopla]):
            out_s = out_s + f"   {n+1}. {peopla.name}\n"

        out_s = out_s + f"...involving {len(self.target_peoplas)} target Peoplas:\n"

        for n, peopla in enumerate(self.target_peoplas):
            out_s = out_s + f"   {n+1}. {peopla.name}\n"

        out_s = out_s + f"...{len(self.evidence_reference)} evidence lines are:\n"

        for n, line_number in enumerate(self.evidence_reference):
            out_s = out_s + f"   {n+1}. {line_number}"

        return out_s

    def generate_summary(self, i):

        agroup_label = f"[AGROUP] [{i:04}] "
        pre = " ".ljust(len(agroup_label))

        s = [
            f"{agroup_label}{'directed' if self.directed else 'undirected'} {self.type} ActionGroup\n"
        ]

        s.append( pre + f"SOURCE   {self.source_peopla.name}\n") 

        target_list = []
        for n, peopla in enumerate(self.target_peoplas):
            target_list.append(peopla.name)

        target_string = ", ".join(target_list)

        s.append( pre + f"TARGET   {len(target_list)}: " + target_string + "\n" )

        evidence_string = ",".join(str(x) for x in self.evidence_reference)

        s.append( pre + f"EVIDENCE {len(self.evidence_reference)}: " + evidence_string + "\n" )

        return ( "".join(s) )

    ### What needs to match for two ActionGroups objects to be considered the same?
    def __eq__(self, other):
        return_result = False

        for self_p in self.target_peoplas:
            if self_p not in other.target_peoplas:
                return False

        if (
            self.type == other.type
            and self.directed == other.directed
            and self.source_peopla.name == other.source_peopla.name
            and len(self.target_peoplas) == len(other.target_peoplas)
        ):

            target_peopla_match_count = 0
            for self_tp in self.target_peoplas:
                for other_tp in self.target_peoplas:
                    if self_tp.peopla_match(other_tp):
                        target_peopla_match_count += 1

            if target_peopla_match_count == len(self.target_peoplas):
                return_result = True

        return return_result

    def print_compact_summary(self, i, annotation=""):  # pragma: no cover
        to_initials = []
        for t in self.target_peoplas:
            to_initials.append("".join([word[0] for word in (t.name).split()]))

        target_string = "(-)"

        if len(to_initials):
            to_initials_list = ",".join(to_initials)
            target_string = f" (+ {to_initials_list})"

        this_reporting_line = (
            f"[AGROUP] / {i+1} / {self.type} / {self.source_peopla.name}{target_string}"
        )

        this_attributes_list = []
        this_evidence_list = self.evidence_reference

        if not len(this_evidence_list):
            this_evidence_list = ["-"]

        if len(self.attributes) > 0:

            for action, these_attributes in self.attributes.items():
                ### action will be the action name
                ### attribute_dictionary will be a dictionary of the form
                ###   {1: {...}, 2: {...}}
                # print( action )
                # print( these_attributes )
                for attribute_dictionary in these_attributes.values():
                    this_attributes_list = list(
                        set(this_attributes_list + list(attribute_dictionary.keys()))
                    )
                    # print(this_attributes_list)

        if not len(this_attributes_list):
            this_attributes_list = ["-"]

        attributes_string = ",".join(this_attributes_list)
        this_reporting_line += " / [" + attributes_string + "]"
        this_reporting_line += (
            " / [" + ",".join(f"{e}" for e in this_evidence_list) + "]"
        )

        if annotation:
            this_reporting_line += f" ! {annotation}"

        this_reporting_line += f"\n"

        return this_reporting_line

    def print_description(self): 
        s_info = f"{'directed' if self.directed else 'undirected'} {self.type} ActionGroup,\n"
        s_info = s_info + f" involving the following source Peoplas\n"

        s_debug = ""
        for n, peopla in enumerate([self.source_peopla]):
            s_debug = s_debug + f"{n}. {peopla}"

        s_info = s_info + f" involving {len(self.target_peoplas)} target Peoplas\n"

        for n, peopla in enumerate(self.target_peoplas):
            s_debug = s_debug + f"{n}. {peopla}"

        return {"info": s_info, "debug": s_debug}

    def add_new_attribute_instance(self, action_text, inheritance):

        logger.info(
            f"NEW Adding attribute to ActionGroup object {self.type}: ({action_text})"
        )

        if action_text in self.attribute_instances:
            print("This is an attribute that we've already seen for this ActionGroup")
            self.attribute_instances[action_text] += 1
        else:
            print("This is a new attribute this ActionGroup")
            self.attributes[action_text] = {}
            self.attribute_instances[action_text] = 1

        this_instance = self.attribute_instances[action_text]

        print(
            f"Is this action already in the attribute dictionary?\n"
            + f"---> in self.attributes? {action_text in self.attributes}\n"
            + f"---> in self.attribute_instances? {action_text in self.attribute_instances}\n"
            f"---> value in attribute_instances? {this_instance}\n"
        )

        self.attributes[action_text][this_instance] = inheritance

        print(f"Adding the following dictionary to attributes:\n")
        print(f">> This instance: {this_instance}\n")
        print(f">> This Action Groups's attributes:\n")
        print(
            log_pretty(
                self.attributes[action_text][self.attribute_instances[action_text]]
            )
        )

        # input()

    def update_attribute(self, attribute_text, d, evidence=None):

        ### We will not have an attribute instance recorded if we
        ### are looking at an inferred attribute (e.g., GENDER from
        ### a gendered Peorel). If that is the case, we need to add
        ### it. If it is already there, that will be because we've
        ### found evidence elsewhere, so we should increment the
        ### instance value.
        if attribute_text not in self.attribute_instances:
            logger.debug(
                f"Starting a new count for {attribute_text} for ActionGroup ({self.type})"
            )
            self.attribute_instances[attribute_text] = 1

        this_instance = self.attribute_instances[attribute_text]

        existing_attributes = {}
        if attribute_text in self.attributes:
            existing_attributes = self.attributes[attribute_text][this_instance]

        ### If we haven't recorded this attribute before, we
        ### need to add it to the attributes dictionary first
        if attribute_text not in self.attributes:
            self.attributes[attribute_text] = {}

        updated_attributes = {**existing_attributes, **d}

        logger.debug(
            f"This is what exists at the moment:{log_pretty(existing_attributes)}"
            f"This is what needs to be added: {log_pretty(d)}"
            f"This is what it is going to look like: {log_pretty(updated_attributes)}"
        )

        self.attributes[attribute_text][this_instance] = updated_attributes


class Peorel:
    """
    A Peorel object - relationship between two people
    """

    def __init__(
        self, peopla_is, peopla_to, relation_text, relation_depth, details_hash=None
    ):

        self.relation_text = relation_text
        self.relation_depth = relation_depth
        self.peopla_is = peopla_is
        self.peopla_to = peopla_to

        ### Attributes of the Peorel itself
        self.attributes = details_hash

        ### Evidence reference (line number from original file)
        self.evidence_reference = []

        logger.info(
            f"Creating a PEOREL object: {self.peopla_is.name} is a {self.relation_text} to {self.peopla_to.name} (depth={self.relation_depth})"
        )

    ### What needs to match for two PEOREL objects to be considered the same?
    def __eq__(self, other):
        return_result = False

        if (
            self.relation_text == other.relation_text
            and self.relation_depth == other.relation_depth
            and self.peopla_is.name == other.peopla_is.name
            and self.peopla_to.name == other.peopla_to.name
            and self.peopla_is.global_id == other.peopla_is.global_id
            and self.peopla_is.local_id == other.peopla_is.local_id
        ):
            return_result = True

        return return_result

    def __str__(self):  # pragma: no cover
        evidence_string = ",".join(str(x) for x in self.evidence_reference)

        s_out = (
            f"{self.peopla_is.name} is a {self.relation_text} to {self.peopla_to.name} "
        )
        s_out = s_out + "[Evidence: " + evidence_string + "]"

        return s_out

    def generate_summary(self, i):
        evidence_string = ",".join(str(x) for x in self.evidence_reference)

        peorel_label = f"[PEOREL] [{i:04}] "

        s = [
            f"{peorel_label}{self.peopla_is.name} is a {self.relation_text} to {self.peopla_to.name} / {evidence_string}\n"
        ]

        return "".join(s)

    def print_compact_summary(self, i, annotation):  # pragma: no cover

        this_reporting_line = f"[PEOREL] / {i+1} / {self.peopla_is.name} is {self.relation_text} to {self.peopla_to.name}"

        evidence_s = ",".join(f"{e}" for e in self.evidence_reference)

        this_reporting_line += f" / [{evidence_s}]"

        if annotation:
            this_reporting_line += f" ! {annotation}"

        this_reporting_line += f"\n"

        return this_reporting_line


class Peopla:
    """
    A Peopla object
    """

    def __init__(self, input, place_flag=False, local_id=None, global_id=None):
        self.type = "place" if place_flag else "person"
        self.name = input

        ### Aggributes of the Peopla itself
        self.attributes = {}
        self.attributes_evidence = {}
        ### Any ActionGroups that are relevant to this Peopla
        self.action_groups = []

        ### IDs for the Peoplas
        self.global_id = global_id
        self.local_id = local_id

        ### Keeping track of attribute instances
        self.attribute_instances = {}

        ### Evidence reference (line number from original file)
        self.evidence_reference = []

        logger.info(
            f"Creating a PEOPLA object: {self.name} ({self.type}) ({self.local_id}) ({self.global_id})"
        )

    def generate_summary(self, i):
        evidence_string = ",".join(str(x) for x in self.evidence_reference)

        peopla_label = f"[PEOPLA] [{i:04}] "
        pre = " ".ljust(len(peopla_label))

        title_s = [ f"{peopla_label}{self.type} {self.name} {{{self.global_id}}} {self.local_id} / {evidence_string}\n" ]
        s = []

        if self.attributes:
            title_width = len(max(self.attributes.keys(),key=len))

            ### For formatting, find longest label first:
            label_width = 8 # this is the length of 'evidence'

            for action, values in self.attributes.items():
                for num, attributes in values.items():
                    if attributes:
                        # label_width = len(max(attributes.keys(),key=len))

                        for label, value in attributes.items():

                            this_info = [f"{action.ljust(title_width)}"]
                            this_info.append( f"{num:02}" )
                            this_info.append( f"{label.ljust(label_width)}" )

                            this_evidence = []
                            if type( value ).__name__ == "list":
                                for this_v in value:
                                    if type( this_v ).__name__ == "Peorel":
                                        e = re.sub("Evidence: ","", format(this_v) )
                                        this_evidence.append(f"{format(e)}")
                                    else:
                                        this_evidence.append( f"{this_v}" )
                                evidence_string = " / ".join(this_evidence)
                                this_info.append( f"{evidence_string}")
                            else:
                                this_info.append( f"{value}" )
                            this_string = " ".join(this_info)

                            s.append(this_string + "\n")

        s = [pre + x for x in s]

        return ( "".join(title_s + s) )

    def new_add_action(self, action_text, inheritance, evidence):

        logger.info(
            f"NEW Adding attribute to PEOPLA object {self.name}: ({action_text})"
        )

        if action_text in self.attribute_instances:
            print("This is an attribute that we've already seen for this Peopla")
            self.attribute_instances[action_text] += 1
            new_instance = self.attribute_instances[action_text]
            self.attributes_evidence[action_text][new_instance] = []

        else:
            print("This is a new attribute this Peopla")
            self.attributes[action_text] = {}
            self.attribute_instances[action_text] = 1
            self.attributes_evidence[action_text] = {}

            new_instance = self.attribute_instances[action_text]
            self.attributes_evidence[action_text][new_instance] = []

        print(
            f"Is this action already in the attribute dictionary?\n"
            + f"---> in self.attributes? {action_text in self.attributes}\n"
            + f"---> in self.attribute_instances? {action_text in self.attribute_instances}\n"
            + f"---> value in attribute_instances? {self.attribute_instances[action_text]}\n"
        )

        # if action_text in self.attributes:
        #     logger.debug(f"This action already exists in the attributes")
        #     self.attributes[action_text] = merge_attributes(
        #         deepcopy(self.attributes[action_text]),
        #         inheritance
        #     )
        # else:
        #     logger.debug(f"This is what is to be inherited:{log_pretty(inheritance)}")
        #     self.attributes[action_text] = inheritance

        self.attributes[action_text][
            self.attribute_instances[action_text]
        ] = inheritance

        self.attributes_evidence[action_text][
            self.attribute_instances[action_text]
        ].append(evidence)

        print(f"Adding the following dictionary to attributes:\n")
        print(f">> This instance: {self.attribute_instances[action_text]}\n")
        print(f">> This Peopla's attributes:\n")
        print(log_pretty(self.attributes))
        print(f">> This Peopla's attributes evidence:\n")
        print(log_pretty(self.attributes_evidence))
        # input()

    def update_attribute(self, attribute_text, d, evidence=None):

        logger.info(
            f"Adding attribute to PEOPLA object {self.name}: ({attribute_text})"
        )

        ### We will not have an attribute instance recorded if we
        ### are looking at an inferred attribute (e.g., GENDER from
        ### a gendered Peorel). If that is the case, we need to add
        ### it. If it is already there, that will be because we've
        ### found evidence elsewhere, so we should increment the
        ### instance value.
        if attribute_text not in self.attribute_instances:
            print(">> Starting a new count for {attribute_text}")
            self.attribute_instances[attribute_text] = 1

            this_instance = self.attribute_instances[attribute_text]
            self.attributes_evidence[attribute_text] = {}
            self.attributes_evidence[attribute_text][this_instance] = []

        this_instance = self.attribute_instances[attribute_text]

        existing_attributes = {}
        if attribute_text in self.attributes:
            existing_attributes = self.attributes[attribute_text][this_instance]

        ### If we haven't recorded this attribute before, we
        ### need to add it to the attributes dictionary first
        if attribute_text not in self.attributes:
            self.attributes[attribute_text] = {}

        updated_attributes = {**existing_attributes, **d}

        logger.debug(
            f"This is what exists at the moment:{log_pretty(existing_attributes)}"
            f"This is what needs to be added: {log_pretty(d)}"
            f"This is what it is going to look like: {log_pretty(updated_attributes)}"
        )

        self.attributes[attribute_text][this_instance] = updated_attributes

        if evidence:
            self.attributes_evidence[attribute_text][this_instance].append(evidence)

    def print_compact_summary(self, i, annotation):  # pragma: no cover
        this_reporting_line = (
            f"[PEOPLA] / {i+1} / {self.name} {{{self.global_id}}} ({self.local_id})"
        )

        p_attributes_list = []

        if len(self.attributes) > 0:

            for action, attribute_dictionary in self.attributes.items():
                ### action will be the action name
                ### attribute_dictionary will be a dictionary of the form
                ###   {1: {...}, 2: {...}}

                p_attribute_evidence_list = []

                for evidence_i in attribute_dictionary.keys():
                    this_evidence = self.attributes_evidence[action][evidence_i]
                    p_attribute_evidence_list.append(this_evidence)

                p_attribute_evidence_list = flatten(p_attribute_evidence_list)

                all_evidence = ",".join(f"{e}" for e in p_attribute_evidence_list)

                tmp_s = f"{action}: {all_evidence}"
                p_attributes_list.append(tmp_s)

        if not len(p_attributes_list):
            p_attributes_list = ["-"]

        this_reporting_line += " / [" + ",".join(p_attributes_list) + "]"

        if annotation:
            this_reporting_line += f" ! {annotation}"

        this_reporting_line += f"\n"

        return this_reporting_line

    def __str__(self):  # pragma: no cover
        s_out = f"{self.type} PEOPLA called {self.name}\n"

        evidence_string = ",".join(str(x) for x in self.evidence_reference)

        s_out = s_out + "Evidence: lines " + evidence_string + "\n"

        if self.global_id:
            s_out = s_out + f"...with the global ID: {self.global_id}\n"
        if self.local_id:
            s_out = s_out + f"...with the local ID: {self.local_id}\n"

        if len(self.attributes) == 0:
            s_out = s_out + f"...with no attributes\n"
        else:
            s_out = (
                s_out
                + f"...and the following attributes:\n{log_pretty(self.attributes)}"
            )

            if "GENDER" in self.attributes:

                s_out = (
                    s_out
                    + f"...further information for gender evidence (if we have it):\n"
                )

                for k, v in self.attributes["GENDER"].items():
                    for i, this_peorel_evidence in enumerate(v["evidence"]):
                        s_out = s_out + f"({i})" + format(this_peorel_evidence) + "\n"

        return s_out

    def peopla_match(self, other):
        return_result = False

        # logger.debug(f"'{self.name}' == '{other.name}' ??\n")
        # logger.debug(f"'{self.type}' == '{other.type}' ??\n")
        # logger.debug(f"'{self.global_id}' == '{other.global_id}' ??\n")
        # logger.debug(f"'{self.local_id}' == '{other.local_id}' ??\n")
        # logger.debug(
        #     f"'{self.evidence_reference}' == '{other.evidence_reference}' ??\n"
        # )

        if (
            self.name == other.name
            and self.type == other.type
            and self.global_id == other.global_id
            and self.local_id == other.local_id
            and self.evidence_reference == other.evidence_reference
        ):
            return_result = True

        return return_result


class Document:
    """
    A Document object
    """

    def __init__(self, file="", settings_file="settings.yaml"):
        """
        Defining a document object
        """

        logger.info(f"Creating a document object from:\n - {file}\n - {settings_file})")

        self.file = file
        self.current_line = 0

        # Read settings file
        logger.info(f"Reading settings file: '{settings_file}'")
        self.add_settings_to_document(settings_file)

        # Information about the sources
        self.header = defaultdict(list)

        # Saving information about shortcuts
        self.shortcut_live = False
        self.shortcuts = []

        #############################################################
        ### Setting up tracking flags and objects                 ###
        #############################################################
        self.current_live_object = []
        self.peopla_live = False
        self.all_peoplas = []
        self.all_action_groups = []
        self.all_peorels = []
        self.current_action = None
        self.current_source_peopla = None
        self.current_target_peoplas = []

        self.current_pedigree_indent = 0
        self.current_breadcrumb_depth = 0
        self.pedigree_breadcrumbs_source = []
        self.pedigree_breadcrumbs_target = []

        self.relation_live = False
        self.relation_text = None
        self.relation_depth = 0

        self.current_leaf_peopla = None
        self.current_leaf_action_group = None
        self.current_action_scope = None

        self.peopla_action_group_live = False
        self.peopla_action_group_directed = False

        #############################################################

        self.current_build_map = {
            "empty": True,
            "ignore": False,
            "header": False,
            "content": False,
        }
        self.missing_relation_flag = False

        #############################################################

        # Saving the data tables
        self.data_table_live = False
        self.data_tables = []

        # Saving the data points
        self.data_points = []

    def add_settings_to_document(self, file):

        logger.info(f"Reading settings file [{file}]")

        settings = read_settings_file(file)

        logger.info(f"{log_pretty(settings)}")

        self.settings_file = file
        self.header_tags = ["TITLE"] + settings["header_tags"]
        self.header_length = len(max(self.header_tags, key=len))

        if settings.get("shortcut_mappings") is not None:
            self.shortcut_mappings = dict(
                pair for d in settings["shortcut_mappings"] for pair in d.items()
            )

            logger.info(f"Shortcut mappings provided:")
            logger.info(f"{log_pretty(self.shortcut_mappings)}")

    def summarise_transition(self, previous): 
        list_of_keys = [
            "empty","ignore","header",
            "content",
            "shortcut","shortcut_def",
            "peopla","relation","action_group",
            "indent_count","tab_count"
        ]

        boolean_mapping = { True: "[X]", False: "[_]"}
        s = []
        title_width = 12
        content_width = 8

        hr = f"+-{'-'.ljust(title_width,'-')}-+-{'-'.ljust(content_width,'-')}-+-{'-'.ljust(content_width,'-')}-+\n"

        s.append( hr )
        s.append( f"| {''.ljust(title_width)} | {'previous'.ljust(content_width)} | {'current'.ljust(content_width)} |\n" )
        s.append( hr )

        for k in list_of_keys:
            this_k = k.ljust(title_width)

            this_current_formatted = ".".ljust(content_width)
            if ( k in self.current_build_map ):
                this_current = self.current_build_map[k] #.ljust(column_width)
                this_current_type = type(this_current).__name__
                if this_current_type != "str":
                    if this_current_type == "bool":
                        this_current = boolean_mapping[this_current]
                    else:
                        this_current = str(this_current)
                this_current_formatted = this_current.ljust(content_width)

            this_previous_formatted = ".".ljust(content_width)
            if ( k in previous ):
                this_previous = previous[k]
                this_previous_type = type(this_previous).__name__
                if type(this_previous).__name__ != "str":
                    if this_previous_type == "bool":
                        this_previous = boolean_mapping[this_previous]
                    else:                    
                        this_previous = str(this_previous)
                this_previous_formatted = this_previous.ljust(content_width)

            s.append( f"| {this_k} | {this_previous_formatted} | {this_current_formatted} |\n" )

        s.append( hr )

        return( s )

    def describe_transition(self, previous):

        if self.current_build_map["content"]:

            previous_indent = 0
            if "indent_count" in previous:
                previous_indent = previous["indent_count"]

            current_indent = self.current_build_map["indent_count"]

            if current_indent > previous_indent:
                print(
                    f"- moved deeper in hierarchy from {previous_indent} to {current_indent}"
                )
            elif current_indent < previous_indent:
                print(
                    f"- moved higher in hierarchy from {previous_indent} to {current_indent}"
                )
            else:
                print(f"- we are at the same level of hierarchy ({previous_indent})")

            previous_tabs = 0
            if "tab_count" in previous:
                previous_tabs = previous["tab_count"]

            current_tabs = self.current_build_map["tab_count"]

            if current_tabs > previous_tabs:
                print(f"- gained tabs, from {previous_tabs} to {current_tabs}")
            elif current_tabs < previous_tabs:
                print(f"- lost tabs, from {previous_tabs} to {current_tabs}")
            else:
                print(f"- same number of tabs ({previous_tabs})")

    def read_document(self, pause_threshold=1):
        """
        Reading a document
        """

        with open(self.file, "r") as d:
            for line in d:

                self.current_line += 1

                for this_rg in human_annotations_to_remove_rg:
                    line = re.sub(this_rg, "", line)

                previous_build_map = deepcopy(self.current_build_map)
                current_build_map = build_map(line)

                if current_build_map["content"]:
                    self.current_build_map = build_map(line)
                    self.describe_transition(previous_build_map)

                    ### We are comparing two lines of content
                    if all(
                        [
                            previous_build_map["content"],
                            self.current_build_map["content"],
                        ]
                    ):
                        ### We have moved back up the hierarchy
                        if (
                            (
                                self.current_build_map["indent_count"]
                                < previous_build_map["indent_count"]
                            )
                            or (
                                self.current_build_map["tab_count"]
                                < previous_build_map["tab_count"]
                            )
                            and (self.current_build_map["peopla"])
                            and (self.current_build_map["indent_count"] > 0)
                        ):
                            self.missing_relation_flag = True
                            print("I have identified a missing relation\n")
                            self.relation_live = False
                            self.peopla_action_group_live = False

                logger.debug(f"Reading line #{self.current_line}: {line.rstrip()}")

                ### Can skip this logic if it's an empty line

                if not re.match(empty_line_regex, line):
                    previous_breadcrumb_depth = self.current_breadcrumb_depth
                    self.current_breadcrumb_depth = get_pedigree_depth(line)

                    ### If we are moving back up the hierarchy, we want to restore
                    ### our target peoplas to what they were (we may have lost them
                    ### when processing information further into the hierarchy).

                    if previous_breadcrumb_depth > self.current_breadcrumb_depth:
                        logger.debug(
                            f"Reversing up the hierarchy (from level {previous_breadcrumb_depth} to {self.current_breadcrumb_depth})"
                            + f"Target peoplas will be restored from level {self.current_breadcrumb_depth} if they exist"
                        )
                        if (
                            len(self.pedigree_breadcrumbs_target)
                            >= self.current_breadcrumb_depth + 1
                        ):
                            logger.debug(
                                f"Target peoplas DO exist at level {self.current_breadcrumb_depth} - restoring"
                            )
                            self.current_target_peoplas = self.pedigree_breadcrumbs_target[
                                self.current_breadcrumb_depth
                            ]
                        else:
                            logger.debug(
                                f"No target peoplas exist at level {self.current_breadcrumb_depth} - setting to []"
                            )
                            self.current_target_peoplas = []

                # input()

                ### We want to capture the scope and then remove it from the line
                ### so that we don't have to accommodate it in the parsing. Because
                ### we can use brackets in tables for local IDs, we do not want to
                ### do this when a data table is live.
                line_unscoped = line
                if not self.data_table_live:
                    [
                        line_unscoped,
                        self.current_action_scope,
                    ] = obtain_and_remove_scope(line)

                logger.debug(f"Amending line to remove scope: {line_unscoped}")

                if self.shortcut_live:
                    if not self.scan_for_shortcut_lines(line_unscoped):
                        self.scan_for_shortcut_definition(line_unscoped)
                else:
                    self.scan_for_shortcut_lines(line_unscoped)

                if self.data_table_live:
                    self.scan_for_data_points(line_unscoped)
                else:
                    if self.peopla_live:
                        self.scan_for_peopla_attributes(line_unscoped)

                    self.scan_for_data_table_header(line_unscoped)

                self.scan_for_header_lines(line_unscoped)
                self.scan_for_peopla_lines(line_unscoped)

                ### It is possible for there to be blank lines inside a peopla
                if not self.peopla_live:
                    self.reset(line)

                self.print_compact_current_status(self.current_line, line, previous_build_map )

                ### If "PYTEST_CURRENT_TEST" exists in os.environ, then
                ### we are currently running test. We don't want to use
                ### the pause functionality if we are running a test.
                if not "PYTEST_CURRENT_TEST" in os.environ:
                    if self.current_line >= pause_threshold:
                        input()

        ### flatten the datapoints into a table here
        self.data_points_df = self.generate_table_from_datapoints()

    def print_current_status(self, n, l):

        status_update = (
            "=================================================================\n"
        )

        ### Headers -------------------------------------------------

        if len(self.header) > 0:
            status_update = (
                status_update + f"There are currently {len(self.header)} header items\n"
            )

            for i, p in enumerate(self.header):
                status_update = status_update + f"Header item ({i}) {p}\n"

        status_update = status_update + f"Just read line number [{n}]\n"
        status_update = status_update + f"The content was [{l}]\n"

        status_update = status_update + "------------------------------------\n"

        status_update = (
            status_update
            + f"There are {len(self.all_peoplas)} Peoplas recorded overall\n"
        )

        for ii, pp in enumerate(self.all_peoplas):
            status_update = status_update + f"---> Peopla #({ii}) {pp.name}\n"

        status_update = status_update + "------------------------------------\n"

        if self.current_source_peopla != None:
            status_update = (
                status_update
                + f"The current source Peopla is {self.current_source_peopla.name}\n"
            )

            for k, v in self.current_source_peopla.attributes.items():
                status_update = (
                    status_update + f"--> Current source peopla attribute ({k}) {v}\n"
                )

        else:
            status_update = status_update + f"There is no current source Peopla\n"

        status_update = status_update + "------------------------------------\n"

        if len(self.current_target_peoplas) > 0:
            status_update = (
                status_update
                + f"There are currently {len(self.current_target_peoplas)} target Peoplas\n"
            )

            for i, p in enumerate(self.current_target_peoplas):
                status_update = status_update + f"({i}) {p.name}\n"

                for j, q in enumerate(p.attributes):
                    status_update = (
                        status_update
                        + f"--> Current target peopla attribute ({i}) {q}\n"
                    )

                    for k, v in (p.attributes)[q].items():
                        status_update = status_update + f"------> ({k}) {v}\n"

        else:
            status_update = status_update + f"There is no current target Peopla\n"

        status_update = status_update + "------------------------------------\n"

        ### Breadcrumbs ---------------------------------------------

        status_update = status_update + f"The current source peopla breadcrumbs:\n"

        num_source_breadcrumbs = len(self.pedigree_breadcrumbs_source)

        status_update = (
            status_update
            + f"---> There are {num_source_breadcrumbs} SOURCE peopla breadcrumbs populated:\n"
        )

        for i, b in enumerate(self.pedigree_breadcrumbs_source):
            status_update = status_update + f"SOURCE [{i}] {format(b)}\n"

        status_update = status_update + "------------------------------------\n"

        status_update = status_update + f"The current target peopla breadcrumbs:\n"

        num_target_breadcrumbs = len(self.pedigree_breadcrumbs_target)

        status_update = (
            status_update
            + f"---> There are {num_target_breadcrumbs} TARGET peopla breadcrumbs populated:\n"
        )

        for i, b in enumerate(self.pedigree_breadcrumbs_target):
            if b:
                for j, bj in enumerate(b):
                    status_update = status_update + f"TARGET [{i}.{j}] {format(bj)}\n"
            else:
                status_update = status_update + f"TARGET [{i}] is absent\n"

        ### Leaf peopla -------------------------------------------------

        status_update = status_update + "------------------------------------\n"

        status_update = status_update + "Current leaf Peoplas\n"
        status_update = status_update + format(self.current_leaf_peopla) + "\n"

        status_update = status_update + "------------------------------------\n"

        status_update = status_update + "Current action scope\n"
        if self.current_action_scope:
            status_update = status_update + self.current_action_scope + "\n"
        else:
            status_update = status_update + "No action scope identified"

        status_update = status_update + "------------------------------------\n"

        status_update = status_update + "Current leaf Action Group\n"
        status_update = status_update + format(self.current_leaf_action_group) + "\n"

        status_update = status_update + "------------------------------------\n"

        ### Peorels -------------------------------------------------

        status_update = (
            status_update
            + f"There are {len(self.all_peorels)} Peorels recorded overall\n"
        )

        for ii, pp in enumerate(self.all_peorels):
            evidence_string = ",".join(str(x) for x in pp.evidence_reference)
            status_update = (
                status_update
                + f"---> Peorel #({ii}) {pp.peopla_is.name} is a {pp.relation_text} to {pp.peopla_to.name} [refs: {evidence_string}]\n"
            )

        status_update = status_update + "------------------------------------\n"

        ### Action groups -------------------------------------------

        if len(self.all_action_groups) > 0:
            status_update = (
                status_update
                + f"There are currently {len(self.all_action_groups)} Action Groups\n"
            )

            for i, p in enumerate(self.all_action_groups):
                status_update = status_update + f"({i}) {p.type}\n"
                status_update = status_update + f"    directed? {p.directed}\n"
                status_update = (
                    status_update + f"    source peopla? {p.source_peopla.name}\n"
                )
                status_update = (
                    status_update + f"    target peoplas? {len(p.target_peoplas)}\n"
                )

                for j, q in enumerate(p.target_peoplas):
                    status_update = (
                        status_update
                        + f"------> target peopla in action group ({i}) {q.name}\n"
                    )

                status_update = (
                    status_update + f"    attributes? length = {len(p.attributes)}\n"
                )

                for k, v in (p.attributes).items():
                    status_update = status_update + f"------> ({k}) {v}\n"

        ### Indicators ----------------------------------------------

        status_update = status_update + "------------------------------------\n"

        relevant_live_indicators = [
            "shortcut_live",
            "peopla_live",
            "peopla_action_group_live",
            "relation_live",
            "data_table_live",
        ]

        for r in relevant_live_indicators:
            status_update = status_update + f"The [{r}] flag is {getattr(self,r)}\n"

        status_update = (
            status_update
            + "================================================================="
        )

        logger.debug(status_update)

        # input()

    def print_compact_current_status(
        self, n, l, previous_build_map, print_header_info=False, specify_objects=True
    ):  # pragma: no cover

        pre = f"[{n:04}] "
        big_break_s = "".rjust(70 - len(pre), "=") + "\n"
        small_break_s = "".rjust(70 - len(pre), "-") + "\n"

        s = [f"LINE: {l}"]
        s.append(big_break_s)

        ### Headers -------------------------------------------------

        if print_header_info:
            if len(self.header) > 0:
                s.append(f"{len(self.header)} header items")

                for i, p in enumerate(self.header):
                    s.append(f"Header ({i}) {p}")

            s.append(big_break_s)

        ### Flags -------------------------------------------------

        relevant_live_indicators = [
            "shortcut_live",
            "peopla_live",
            "peopla_action_group_live",
            "relation_live",
            "data_table_live",
            "missing_relation_flag",
        ]

        for r in relevant_live_indicators:
            r_val = "X" if getattr(self, r) else "_"
            s.append(f"[{r_val}] / {r} \n")

        s.append(small_break_s)

        ### Current action scope -------------------------------------------------

        s.append(
            f"Current action [{self.current_action}] and scope [{self.current_action_scope}]\n"
        )
        s.append(big_break_s)

        ### Objects -------------------------------------------------

        s.append(
            f"{len(self.all_peoplas)} Peoplas | "
            + f"{len(self.all_peorels)} Peorels | "
            + f"{len(self.all_action_groups)} Action Groups\n"
        )

        s.append(small_break_s)

        if specify_objects:
            ### Print peoplas
            for i, o in enumerate(self.all_peoplas):
                annotation_list = []
                if o == self.current_source_peopla:
                    annotation_list.append("SRC")
                if o in self.current_target_peoplas:
                    annotation_list.append("TRG")
                if o == self.current_leaf_peopla:
                    annotation_list.append("LEAF")
                if type(o).__name__ == type(self.current_live_object).__name__:
                    if o == self.current_live_object:
                        annotation_list.append("LIVE")

                annotation = "|".join(annotation_list)

                s.append(o.print_compact_summary(i, annotation))
            s.append(small_break_s)
            ### Print peorels
            for i, o in enumerate(self.all_peorels):
                annotation_list = []
                if type(o).__name__ == type(self.current_live_object).__name__:
                    if o == self.current_live_object:
                        annotation_list.append("LIVE")

                annotation = "|".join(annotation_list)

                s.append(o.print_compact_summary(i, annotation))
            s.append(small_break_s)
            ### Print Action Groups
            for i, o in enumerate(self.all_action_groups):
                annotation_list = []
                if o == self.current_leaf_action_group:
                    annotation_list.append("LEAF")
                if type(o).__name__ == type(self.current_live_object).__name__:
                    if o == self.current_live_object:
                        annotation_list.append("LIVE")

                annotation = "|".join(annotation_list)

                s.append(o.print_compact_summary(i, annotation))

        s.append(big_break_s)

        ### Breadcrumbs -------------------------------------------------

        source_breadcrumb_title = ""
        source_breadcrumb_content = ""

        for i, b in enumerate(self.pedigree_breadcrumbs_source):

            source_breadcrumb_title += f"{i}".ljust(10)
            source_breadcrumb_content += b.name.ljust(10)

        if len(source_breadcrumb_title) > 0:
            s.append("[SOURCE BREADCRUMB] " + source_breadcrumb_title + "\n")
            s.append("[SOURCE BREADCRUMB] " + source_breadcrumb_content + "\n")

        s.append(small_break_s)

        target_breadcrumb_title = ""
        target_breadcrumb_content = ""

        for i, b in enumerate(self.pedigree_breadcrumbs_target):
            this_list = []

            if b:
                for bj in b:
                    this_list.append("".join([word[0] for word in (bj.name).split()]))

            this_list_string = ",".join(this_list)

            target_breadcrumb_title += f"{i}".ljust(10)
            target_breadcrumb_content += this_list_string.ljust(10)

        if len(target_breadcrumb_title) > 0:
            s.append("[TARGET BREADCRUMB] " + target_breadcrumb_title + "\n")
            s.append("[TARGET BREADCRUMB] " + target_breadcrumb_content + "\n")

        s.append(big_break_s)

        ### Breadcrumbs -------------------------------------------------
        for t in self.data_tables:
            s.append( f"[DATA] {format(t)}\n" )

        if self.data_points:
            s.append( f"[DATA] {len(self.data_points)} data points\n" )      

        s.append(big_break_s)

        s =  s + self.summarise_transition(previous_build_map)

        s = [pre + x for x in s]
        logger.debug("".join(s))

    def reset(self, line):  # pragma: no cover
        logger.debug(f"Considering reset with: '{line}'")

        if re.match(empty_line_regex, line):
            if self.peopla_live:
                logger.debug("Resetting peopla")
            if self.data_table_live:
                logger.debug("Resetting data table")
            if self.shortcut_live:
                shortcut_dictionary = {}
                for s in self.shortcuts:
                    shortcut_dictionary.update(s)
                self.shortcuts = shortcut_dictionary
                logger.debug("Resetting shortcut")
                logger.debug(
                    f"Shortcut dictionary has been created: {shortcut_dictionary}"
                )

            self.peopla_live = False
            self.data_table_live = False
            self.shortcut_live = False
            self.relation_live = False

            self.current_leaf_peopla = None
            self.current_leaf_action_group = None
            self.current_relation_text = None
            self.current_relation_depth = 0
            self.current_breadcrumb_depth = 0
            self.current_pedigree_indent = math.inf

    def scan_for_shortcut_lines(self, line):
        """
        Function that examines the current input file from file.
        If its format corresponds to a shortcut definition,
        a new shortcut object will be created and added to the
        list of shortcuts that are attached to the Document.
        """
        if re.match(shortcut_line_regex, line):
            logger.debug(f"Identified shortcut line: '{line}'")

            m = re.search(r"^###\t\^(\d+):$", line)
            shortcut_id = m.group(1)
            logger.debug(f"with shortcut id: {shortcut_id}")

            self.shortcut_live = True
            self.shortcuts.append({shortcut_id: {}})
            return True
        else:
            return False

    def create_inheritance_hash(self, flag):
        h = {}
        if flag == "*":
            h = dict(self.header)
            h.pop("TITLE", None)
        return h

    def scan_for_shortcut_definition(self, line):
        if re.match(shortcut_definition_regex, line):
            logger.debug("Found a short cut definition")

            current_shortcut = self.shortcuts[-1]
            current_shortcut_key = list(current_shortcut.keys())[0]

            m = re.search(r"^###\s*(\!?)([^\*]+)(\*?)$", line)

            property_flag = m.group(1).rstrip()
            action_text = m.group(2).rstrip()
            inheritance_flag = m.group(3).rstrip()

            logger.debug(
                f"Identified shortcut content: '{property_flag}' / '{action_text}' / '{inheritance_flag}'"
            )

            inheritance_hash = {}

            if property_flag == "!":
                logger.debug(f"a property: {action_text}")
                k = self.shortcut_mappings[action_text]
                inheritance_hash = {k: action_text}
            elif inheritance_flag == "*":
                logger.debug(f"the header is: {dict(self.header)}")
                logger.debug(f"self shortcuts: {current_shortcut_key}")

                inheritance_hash = {
                    action_text: self.create_inheritance_hash(inheritance_flag)
                }
            else:
                logger.warning(f"shortcut format not recognised: {line}")

            (self.shortcuts[-1])[current_shortcut_key].update(inheritance_hash)
            logger.debug("Setting self.shortcuts in scan_for_shortcut_definition to:")
            logger.debug(self.shortcuts)

    def scan_for_data_table_header(self, line):
        """
        Function that exmaines the current input file from file.
        If it's format corresponds to the header of a data table,
        a new object will be created and added to the list of
        data tables that are attached to the Document.
        """

        if re.match(data_table_header_regex, line):

            ### We can handle more than one shortcut
            m = re.search(
                rf"^###{re.escape(data_point_separator)}([^\^]*)([\^\d]+)$", line
            )

            header_content = m.group(1)
            header_shortcuts = list(filter(None, m.group(2).split("^")))
            header_columns = header_content.split(data_point_separator)
            logger.debug(f"Identified table header: '{header_content}'")
            logger.debug(f"with {len(header_columns)} columns")
            logger.debug(f"with shortcut: {header_shortcuts}")

            logger.debug(f"Shortcuts are: {log_pretty(self.shortcuts)}\n")

            logger.debug(
                f"Is/are the header shortcut(s) ({header_shortcuts}) correct?????"
            )

            ### check: are all the shortcuts present in the table header
            ###        actually defined in the document header?

            check = all(e in list(self.shortcuts.keys()) for e in header_shortcuts)

            if check:
                logger.debug(
                    f"--> All shortcut keys ({','.join(header_shortcuts)}) have been defined in the header"
                )
            else:
                missing_definitions = [
                    e for e in header_shortcuts if e not in list(self.shortcuts.keys())
                ]
                logger.debug(
                    f"--> Some shortcut keys ({','.join(missing_definitions)}) have been NOT been defined in the header"
                )
                logger.debug(self.shortcuts)

            ### Extract only the shortcut information required for this table
            relevant_header_shortcuts = {k: self.shortcuts[k] for k in header_shortcuts}
            logger.debug(
                "Extracting only the shortcut information required for this table\n"
            )
            logger.debug(relevant_header_shortcuts)

            ### Combine the shortcut information into one dictionary (this is necessary where
            ### more than one shortcut marker has been applied to the table)
            relevant_header_shortcuts_combined = {}
            for d in relevant_header_shortcuts.values():
                relevant_header_shortcuts_combined.update(d)

            logger.debug("Combine the header shortcut information\n")
            logger.debug(relevant_header_shortcuts_combined)

            ### Add the definition of this table to the document
            self.data_tables.append(
                DataTable(header_columns, relevant_header_shortcuts_combined)
            )

            self.peopla_live = False
            self.data_table_live = True

    def scan_for_data_points(self, line):
        logger.debug(f"Looking for data table content in {line}")

        current_table = self.data_tables[-1]

        if re.match(data_table_end_regex, line):
            logger.debug("End of table")
            self.data_table_live = False
        elif re.match(data_table_linebreak_regex, line):
            logger.debug("Ignore (line break not relevant)")
        elif re.match(ignore_line_regex, line):
            logger.debug("Ignore (line starts with !)")
        elif re.match(data_table_global_id_regex, line) or re.match(
            data_table_local_id_regex, line
        ):
            ### Check for a global ID
            m = re.search(r"\{(.*)\}", line)
            if m:
                global_id = m.group(1).rstrip()
                logger.debug(f"Found a global identifer: {global_id}")
                self.data_points[-1].add_global_id(global_id)

            ### Check for a local ID
            m = re.search(r"\((.*)\)", line)
            if m:
                local_id = m.group(1).rstrip()
                logger.debug(f"Found a local identifer: {local_id}")
                self.data_points[-1].add_local_id(local_id)
        else:
            content_list = re.split("\t+", line.rstrip())
            logger.debug(f"Found {len(content_list)} data points for the table")
            logger.debug(
                f"This is the current table attributes: {current_table.attributes}"
            )
            self.data_points.append(DataPoint(content_list, current_table))

    def generate_table_from_datapoints(self):
        datapoint_table = pd.DataFrame()

        for d in self.data_points:
            d_dict_tuples = flatten_dict(d.cells)
            d_dict_flat = {}
            for k, v in d_dict_tuples.items():
                new_key = "_".join(k)
                d_dict_flat[new_key] = v
            d_df = pd.DataFrame.from_dict(d_dict_flat)

            d_df["global_id"] = d.global_id
            d_df["local_id"] = d.local_id

            datapoint_table = pd.concat([datapoint_table, d_df])

        return datapoint_table.reset_index().drop(columns=["index"])

    def scan_for_peopla_attributes(self, line):

        logger.debug(f"Looking for peopla attributes in {line}")
        logger.debug(f"Current pedigree indent {self.current_pedigree_indent}")
        logger.debug(f"Current action scope {self.current_action_scope}")

        if re.match(peopla_relation_line_regex, line):
            logger.debug("Found a peopla relationship")
            ### No need to update self.current_live_object

            relation_details = extract_relation_details(line)

            logger.debug(
                f"Identified that a '{relation_details['relation_text']}' relationship is now live"
            )
            logger.debug(
                f"Context will dictate which Peopla are involved in that Peorel"
            )

            self.current_relation_text = relation_details["relation_text"]
            self.current_relation_depth = relation_details["relation_depth"]
            # self.current_pedigree_indent = count_indent(line)

            self.relation_live = True

        elif re.match(peopla_relation_target_regex, line) and self.relation_live:
            ### If we're in here, we've got a relation open
            ### AND we have found what the target is of that relation

            peopla_content_parsed = extract_peopla_details(line)

            ### Who is the target of the relation?
            relation_peopla_is_tmp = Peopla(
                peopla_content_parsed["content"],
                peopla_content_parsed["place_flag"],
                peopla_content_parsed["local_id"],
                peopla_content_parsed["global_id"],
            )

            relation_peopla_is = self.record_peopla(relation_peopla_is_tmp)
            record_evidence(relation_peopla_is, self.current_line)

            self.current_leaf_peopla = relation_peopla_is
            self.current_live_object = self.current_leaf_peopla

            logger.debug(
                f"Found the target of a relation action: '{relation_peopla_is.name}'"
            )
            logger.debug(
                f"This will be in relation to the {self.current_relation_text} relation (depth={self.current_relation_depth})"
            )
            logger.debug(f"But need to work out who the 'to' Peopla is")

            ### Creating this here so that we can catch it and record it as evidence
            ### in the case of gendered relations
            new_peorel = []

            ### This is where we have a relation attached directly to a single Peopla
            if not self.peopla_action_group_live:

                logger.debug(
                    f"The context tells us that the 'to' peopla for this peorel is the current source peopla: {self.current_source_peopla}"
                )

                relevant_source_peopla = self.pedigree_breadcrumbs_source[
                    self.current_breadcrumb_depth - 1
                ]

                # print(
                #     f"*** The 'is' peopla is {relation_peopla_is.name}\n",
                #     f"*** The 'to' peopla will be the the source peopla (there is no target for this relation)\n",
                #     f"*** The current_source_peopla is {self.current_source_peopla.name}\n",
                #     f"*** The current_source_peopla (as breadcrumbs) is\n",
                #     self.print_source_breadcrumbs(),
                #     f"*** The current breadcrumb depth is {self.current_breadcrumb_depth}\n",
                #     f"*** The relevant source peopla is {relevant_source_peopla.name}\n",
                # )

                peorel_tmp = Peorel(
                    relation_peopla_is,
                    relevant_source_peopla,
                    self.current_relation_text,
                    self.current_relation_depth,
                )

                this_new_peorel = self.record_peorel(peorel_tmp)
                record_evidence(this_new_peorel, self.current_line)
                new_peorel.append(this_new_peorel)

            ### This is where we have a relation attached to an open ActionGroup
            ### It will be indicated with a ( as to whether the relation refers to
            ### to the target Peopla(s) only or to the source AND target peoplas
            else:

                # relation_scope = extract_relation_scope(line)
                relation_scope = self.current_action_scope

                logger.debug(
                    f"The context tells us that the 'to' peopla for this peorel is something to do with the target peopla"
                )

                logger.debug(f"The scope for this is: {relation_scope}")

                relevant_to_peopla_list = deepcopy(
                    self.pedigree_breadcrumbs_target[
                        (self.current_breadcrumb_depth - 1)
                    ]
                )
                tt = ""
                for n, x in enumerate(self.current_target_peoplas):
                    tt = f"{tt}[{n}] {x.name}\n"

                # print(
                #     f"*** The 'is' peopla is {relation_peopla_is.name}\n",
                #     f"*** The 'to' peopla will be source AND target peopla\n",
                #     f"*** There are {len(self.current_target_peoplas)} current_target_peoplas\n",
                #     tt,
                #     f"*** The current_target_peopla (as breadcrumbs) is\n",
                #     self.print_target_breadcrumbs(),
                #     f"*** The current breadcrumb depth is {self.current_breadcrumb_depth}\n",
                #     f"*** There are {len(relevant_to_peopla_list)} relevant target_peopla\n",
                # )

                logger.debug("Current to_peopla_list (step 1) - the target peoplas")
                logger.debug(relevant_to_peopla_list)

                # if relation_scope == "target":
                if relation_scope == "leaf":
                    logger.debug(
                        f"This information is only relevant for the target peopla"
                    )
                    logger.debug(f"No need to do anything more")
                else:
                    logger.debug(
                        f"This information is relevant for the source and target peopla"
                    )
                    logger.debug(
                        f"Need to add the current source peopla to the 'to' list"
                    )

                    relevant_source_peopla = self.pedigree_breadcrumbs_source[
                        (self.current_breadcrumb_depth) - 1
                    ]

                    relevant_to_peopla_list.append(relevant_source_peopla)
                    logger.debug(
                        "Current to_peopla_list (step 2) - adding the source peoplas"
                    )
                    logger.debug(relevant_to_peopla_list)

                    # print(
                    #     f"*** The context indicated that the source people needed to be added as well\n",
                    #     f"*** The current_source_peopla is {self.current_source_peopla.name}\n",
                    #     f"*** The current_source_peopla (as breadcrumbs) is\n",
                    #     self.print_source_breadcrumbs(),
                    #     f"*** The current breadcrumb depth is {self.current_breadcrumb_depth}\n",
                    #     f"*** There are now {len(relevant_to_peopla_list)} relevant 'to' peopla\n",
                    # )

                for this_to_peopla in set(relevant_to_peopla_list):
                    peorel_tmp = Peorel(
                        relation_peopla_is,
                        this_to_peopla,
                        self.current_relation_text,
                        self.current_relation_depth,
                    )

                    this_new_peorel = self.record_peorel(peorel_tmp)
                    record_evidence(this_new_peorel, self.current_line)
                    new_peorel.append(this_new_peorel)

            ### If we have a gendered relation, we can augment the Peopla with this
            ### Gender information. The evidence for this (i.e., the relevant Peorel
            ### objects should be recorded alongside this inference).

            relation_peopla_is.update_attribute(
                "GENDER",
                {
                    "value": gender_inference_from_relation(self.current_relation_text),
                    "evidence": new_peorel,
                },
            )

            self.relation_live = False
            self.current_relation_text = None
            self.current_relation_depth = 0
            self.current_pedigree_indent = math.inf

        elif re.match(action_attribute_regex, line):
            logger.debug("Found an attribute of an action")
            logger.debug(
                f"This will be in relation to the {self.current_action} action"
            )

            # action_scope = extract_action_scope(line)
            action_scope = self.current_action_scope

            line_content = re.sub(r"^###[\s]+", "", line)
            info = extract_attribute_information(line_content)
            logger.debug(f"Identified '{self.current_action}' / '{info}' ")

            if self.peopla_action_group_live:

                # if action_scope == "both":
                if action_scope == "full":
                    ### This is an attribute for an action that occurs between
                    ### members of an action group. We need to update the action
                    ### group to have this attribute. So:
                    ### 1. Find the action group
                    ### 2. Add the attributes

                    self.all_action_groups[-1].update_attribute(
                        self.current_action, info
                    )

                elif action_scope == "leaf":
                    ### This is only relevant for the LAST target peoplas
                    ### We need to add an attribute to a peopla

                    self.current_target_peoplas[-1].update_attribute(
                        self.current_action, info, self.current_line
                    )

                    logger.debug(
                        f"Adding [{self.current_action}] attribute to {self.current_target_peoplas[-1].name}"
                    )

            else:
                ### This is an attribute for an action that belongs to a Peopla
                ### that is not part of an action group. So:
                ### 1. Find the Peopla
                ### 2. Add the attributes

                self.current_source_peopla.update_attribute(
                    self.current_action, info, self.current_line
                )

        elif re.match(peopla_attribute_regex, line):
            logger.debug("Found a peopla attribute")

            # action_scope = extract_action_scope(line)
            action_scope = self.current_action_scope
            action_details = extract_action_details(line)

            self.current_action = action_details["action_text"]

            logger.debug(f"The action scope is {action_scope}")
            logger.debug(
                f"Identified '{action_details['action_text']}' / '{action_details['inheritance_flag']}'"
            )

            inheritance_hash = {}
            if action_details["inheritance_flag"]:
                inheritance_hash = self.header
                inheritance_hash.pop("TITLE")

            ### What we have found here is an action of an action group
            if self.peopla_action_group_live:
                # if action_scope == "both":

                if action_scope == "full":

                    ### This is a description of an action between an action group
                    ### We need to make a action_group

                    ag_tmp = ActionGroup(
                        action_details["action_text"],
                        directed=self.peopla_action_group_directed,
                        source_peopla=self.current_source_peopla,
                        target_peoplas=self.current_target_peoplas,
                        # attributes=inheritance_hash,
                    )

                    # self.all_action_groups = self.all_action_groups + [ag]
                    ag = self.record_action_group(ag_tmp)
                    record_evidence(ag, self.current_line)

                    print("THIS IS THE OUTER INHERITANCE HASH:\n")
                    print(deepcopy(dict(inheritance_hash)))

                    ag.add_new_attribute_instance(
                        action_details["action_text"], deepcopy(dict(inheritance_hash))
                    )

                    print("=========================\n")
                    print(ag.attributes)
                    print("=========================\n")

                    # input()

                    self.current_leaf_action_group = ag

                    o = ag.print_description()
                    logger.info(o["info"])
                    logger.debug(o["debug"])

                # elif action_scope == "target":
                elif action_scope == "leaf":
                    ### This is only relevant for the LAST target peoplas
                    ### We need to add an attribute to a peopla

                    self.current_action = action_details["action_text"]

                    for tp in self.current_target_peoplas:
                        logger.debug(
                            f"Adding [{action_details['action_text']}] attribute to {tp.name}"
                        )

                        tp.update_attribute(
                            self.current_action,
                            deepcopy(inheritance_hash),
                            self.current_line,
                        )

            ### What we have found here is an action of a Peopla
            ### (the current Source peopla)
            else:
                self.current_action = action_details["action_text"]
                self.current_source_peopla.new_add_action(
                    action_details["action_text"], inheritance_hash, self.current_line
                )

            # Maybe this shouldn't be removed????
            # self.peopla_live = True

        elif re.match(action_group_regex, line):
            logger.debug("Found an ActionGroup")

            # peopla_content = remove_all_leading_markup(line)
            # logger.debug(f"Parsed out this content: {peopla_content}")

            peopla_content_parsed = extract_peopla_details(line)
            direction_flag = is_action_group_directed(line)

            target_peopla_tmp = Peopla(
                peopla_content_parsed["content"],
                peopla_content_parsed["place_flag"],
                peopla_content_parsed["local_id"],
                peopla_content_parsed["global_id"],
            )

            target_peopla = self.record_peopla(target_peopla_tmp)
            record_evidence(target_peopla, self.current_line)

            self.current_leaf_peopla = target_peopla

            ### If we are staying at the same level of hierarchy,
            ### we want to append to current_target_peoplas. However,
            ### if we are moving up/down the hierarchy, we want to
            ### reset the current_target_peoplas so that it only contains
            ### the one current target peopla that has just been found.

            self.current_target_peoplas = self.current_target_peoplas + [target_peopla]

            new_target_peoplas = [target_peopla]

            ### Update the target breadcrumbs
            self.pedigree_breadcrumbs_target = update_breadcrumbs(
                deepcopy(self.pedigree_breadcrumbs_target),
                self.current_breadcrumb_depth,
                new_target_peoplas,
                "TARGET",
            )

            ### Open an action group
            self.peopla_action_group_live = True
            self.peopla_action_group_directed = direction_flag

        elif (
            re.match(peopla_pedigree_attribute_regex, line)
            and count_indent(line) > self.current_pedigree_indent
        ):
            logger.debug("Found an attribute of an action IN A PEDIGREE")
            logger.debug(
                f"This will be added to {self.current_leaf_peopla.name} (the current pedigree target)"
            )

            # action_scope = extract_action_scope(line)
            # action_scope = self.current_action_scope

            line_content = re.sub(r"^###[\s>]+", "", line)
            info = extract_attribute_information(line_content)
            logger.debug(f"Identified '{self.current_action}' / '{info}' ")

            self.current_leaf_peopla.update_attribute(
                self.current_action, info, self.current_line
            )

            logger.debug(
                f"Adding [{self.current_action}] attribute to {self.current_leaf_peopla.name}"
            )

            # input()

        elif (
            re.match(peopla_pedigree_attribute_regex, line)
            and count_indent(line) <= self.current_pedigree_indent
        ):
            logger.debug("Found a peopla attribute INSIDE A PEDIGREE")

            action_scope = self.current_action_scope
            action_details = extract_pedigree_action_details(line)

            self.current_action = action_details["action_text"]
            self.current_pedigree_indent = count_indent(line)

            logger.debug(f"The action scope is {action_scope}")
            logger.debug(
                f"Identified '{action_details['action_text']}' / '{action_details['inheritance_flag']} / '{action_details['pedigree_depth']}'"
            )

            inheritance_hash = {}
            if action_details["inheritance_flag"]:
                inheritance_hash = self.header
                inheritance_hash.pop("TITLE")

            if self.relation_live:
                ### If there is an action within a pedigree and there is no
                ### target group that is live, it is relevant ONLY for the 'is'
                ### Peopla in the relation.

                logger.debug(
                    f"Adding [{action_details['action_text']}] attribute to pedigree object {self.current_leaf_peopla.name}"
                )
                self.current_leaf_peopla.update_attribute(
                    self.current_action, deepcopy(inheritance_hash), self.current_line
                )
            elif self.current_target_peoplas == []:
                logger.debug(
                    f"Adding [{action_details['action_text']}] attribute to pedigree object {self.current_leaf_peopla.name}"
                )
                self.current_leaf_peopla.update_attribute(
                    self.current_action, deepcopy(inheritance_hash), self.current_line
                )
            elif self.peopla_action_group_live:

                action_scope = self.current_action_scope

                # if action_scope == "both":
                if action_scope == "full":

                    relevant_source_peopla = self.pedigree_breadcrumbs_source[
                        (self.current_breadcrumb_depth)
                    ]

                    ag_tmp = ActionGroup(
                        action_details["action_text"],
                        directed=self.peopla_action_group_directed,
                        source_peopla=relevant_source_peopla,  # self.current_source_peopla,
                        target_peoplas=self.current_target_peoplas,
                        # attributes=deepcopy(inheritance_hash),
                    )
                    # self.all_action_groups = self.all_action_groups + [ag]

                    ag = self.record_action_group(ag_tmp)
                    record_evidence(ag, self.current_line)

                    ag.add_new_attribute_instance(
                        action_details["action_text"], deepcopy(dict(inheritance_hash))
                    )

                    self.current_leaf_action_group = ag
                    self.current_live_object = self.current_leaf_action_group

                    o = ag.print_description()
                    logger.info(o["info"])
                    logger.debug(o["debug"])

                    ### This is an attribute for an action that occurs between
                    ### members of an action group. We need to update the action
                    ### group to have this attribute. So:
                    ### 1. Find the action group
                    ### 2. Add the attributes

                    # self.all_action_groups[-1].update_attribute(
                    #     self.current_action, info
                    # )

                elif action_scope == "leaf":
                    ### This is only relevant for the LAST target peoplas
                    ### We need to add an attribute to a peopla

                    if len(self.current_target_peoplas) > 0:

                        self.current_target_peoplas[-1].update_attribute(
                            self.current_action,
                            deepcopy(inheritance_hash),
                            self.current_line,
                        )

                        logger.debug(
                            f"Adding [{self.current_action}] attribute to {self.current_target_peoplas[-1].name}"
                        )
                    else:

                        logger.debug(
                            f"Adding [{action_details['action_text']}] attribute to pedigree object {self.current_leaf_peopla.name}"
                        )
                        self.current_leaf_peopla.update_attribute(
                            self.current_action,
                            deepcopy(inheritance_hash),
                            self.current_line,
                        )

            ### Then as we encounter attribute of attribute lines that are inside a
            ### we will update these same Peoplas with those attributes of attributes

            ### All updating of attributes will be done by the update_attribute() function

            ### Note that self.current_pedigree_peoplas will need to be set to [] at the
            ### appropriate point - probably when we encounter a source Peopla???

            # input()
        elif self.missing_relation_flag:
            logger.debug("Need to deal with a missing relation")

            # input()

        elif re.match(peopla_embedded_attribute_regex, line):
            logger.debug("Found an embedded attribute INSIDE A PEDIGREE")

            action_scope = self.current_action_scope
            action_details = extract_pedigree_action_details(line)

            # self.current_action = action_details["action_text"]
            # self.current_pedigree_indent = count_indent(line)

            info = extract_attribute_information(action_details["action_text"])
            logger.debug(f"Identified '{self.current_action}' / '{info}' ")

            print(self.current_live_object)
            logger.debug(
                f"Adding [{action_details['action_text']}] embedded attribute to the current live object\n"
            )

            self.current_live_object.update_attribute(self.current_action, info)

            # input()

            # if self.peopla_action_group_live:
            #     logger.debug(
            #         f"Adding [{action_details['action_text']}] embedded attribute to the current leaf action group {self.current_leaf_action_group.type}"
            #     )
            #     self.current_leaf_action_group.update_attribute(
            #         self.current_action, info
            #     )

            # else:
            #     logger.debug(
            #         f"Adding [{action_details['action_text']}] embedded attribute to the current leaf peopla {self.current_leaf_peopla.name}"
            #     )
            #     self.current_leaf_peopla.update_attribute(
            #         self.current_action, info
            #     )

    def record_peopla(self, p):

        peopla_ref = p
        already_recorded = False

        for this_p in self.all_peoplas:
            if this_p.name == p.name and (
                this_p.local_id == p.local_id or this_p.global_id == p.global_id
            ):
                already_recorded = True
                peopla_ref = this_p
                break

        if not already_recorded:
            logger.debug(f"This is a new Peopla that should be recorded ({p.name})")
            self.all_peoplas = self.all_peoplas + [peopla_ref]
        else:
            logger.debug(f"We have already seen this peopla ({p.name})")

        return peopla_ref

    def record_action_group(self, ag):

        action_group_ref = ag
        already_recorded = False

        for this_ag in self.all_action_groups:
            if this_ag == ag:
                already_recorded = True
                action_group_ref = this_ag
                break

        if not already_recorded:
            logger.debug(
                f"This is a new Action Group that should be recorded ({ag.type})"
            )
            self.all_action_groups = self.all_action_groups + [action_group_ref]
        else:
            logger.debug(f"We have already seen this Action Group ({ag.type})")

        return action_group_ref

    def print_source_breadcrumbs(self):
        n = len(self.pedigree_breadcrumbs_target)

        o = f"BREADCRUMBS | SOURCE | {n} populated breadcrumbs\n"

        for i, b in enumerate(self.pedigree_breadcrumbs_source):
            o = o + f"BREADCRUMBS | SOURCE | [{i}] {format(b)}\n"

        return o

    def print_target_breadcrumbs(self):
        n = len(self.pedigree_breadcrumbs_target)

        o = f"BREADCRUMBS | TARGET | {n} populated breadcrumbs\n"

        for i, b in enumerate(self.pedigree_breadcrumbs_target):
            if b:
                for j, bj in enumerate(b):
                    o = o + f"BREADCRUMBS | TARGET | [{i}.{j}] {format(bj)}\n"
            else:
                o = o + f"BREADCRUMBS | TARGET | [{i}] is absent\n"

        return o

    def record_peorel(self, pr):

        peorel_ref = pr
        already_recorded = False

        for this_peorel in self.all_peorels:
            if this_peorel == pr:
                already_recorded = True
                peorel_ref = this_peorel
                break

        if not already_recorded:
            logger.debug(
                f"This is a new Peorel that should be recorded ({pr.peopla_is.name} is {pr.relation_text} to {pr.peopla_to.name})"
            )
            self.all_peorels = self.all_peorels + [peorel_ref]
        else:
            logger.debug(
                f"We have already seen this peorel ({pr.peopla_is.name} is {pr.relation_text} to {pr.peopla_to.name})"
            )

        return peorel_ref

    def scan_for_peopla_lines(self, line):
        """
        Function that exmaines the current input file from file.
        If it's format corresponds to PEOPLA line, a new object
        will be created and added to the list of PEOPLA that are
        attached to the Document.
        """
        if re.match(peopla_line_regex, line):

            peopla_content_parsed = extract_peopla_details(line)

            source_peopla_tmp = Peopla(
                peopla_content_parsed["content"],
                peopla_content_parsed["place_flag"],
                peopla_content_parsed["local_id"],
                peopla_content_parsed["global_id"],
            )

            source_peopla = self.record_peopla(source_peopla_tmp)
            record_evidence(source_peopla, self.current_line)

            self.current_leaf_peopla = source_peopla

            #########################################################

            ### If we're making a new Peopla object and we're at the top level,
            ### then everything needs to be reset.
            ### We don't want to reset everything otherwise, as we might be in
            ### a string of relations and we don't want to loose the existing source
            ### and target Peoplas (see the test test_gender_evidence_is_correct()
            ### for example of a string of relations).

            this_depth = len(re.findall(peopla_relation_depth_regex, line))

            if this_depth == 0:
                ### (1) reset what our source and target peoplas are
                self.current_source_peopla = source_peopla
                self.current_target_peoplas = []

                ### (2) reset relevant live flags
                self.peopla_live = True
                self.peopla_action_group_live = False
                self.relation_live = False
                self.relation_depth = 0
                self.missing_relation_flag = False

                ### (3) reset the source/target breadcrumbs
                self.pedigree_breadcrumbs_source = []
                self.pedigree_breadcrumbs_source.append(source_peopla)
                self.pedigree_breadcrumbs_target = []
            else:
                ### If we have moved further into the hierarchy than
                ### the last time that the current_target_peoplas were
                ### updated, then we want to reset the current_target_peoplas
                ### otherwise we want to keep accumulating the target peoplas

                self.pedigree_breadcrumbs_source = update_breadcrumbs(
                    deepcopy(self.pedigree_breadcrumbs_source),
                    this_depth,
                    deepcopy(source_peopla),
                    "SOURCE",
                )

                new_target_list = deepcopy(self.pedigree_breadcrumbs_target)[
                    :this_depth
                ]

                self.pedigree_breadcrumbs_target = new_target_list
                self.current_target_peoplas = []

    def scan_for_header_lines(self, line):
        """
        Function that examines the current input file from file.
        If it's format corresponds to one of the header formats,
        appropriate slots in the corresponding Document objects
        `header` dictionary will be updated with appropriate text.
        """
        if line.startswith("#["):
            m = re.search(r"\[(.*?)\]", line)
            content = m.group(1)
            self.header["TITLE"].append(content)
            logger.info(f"Adding TITLE header attribute '{content}'")
        elif re.match(header_line_regex, line):
            m = re.search(r"^##(.*?):\s+(.*?)$", line)
            flag = m.group(1)
            content = m.group(2)
            self.header[flag].append(content)
            logger.info(f"Adding {flag} header attribute '{content}'")

    def print_header_information(self):
        """
        Printing the header information for a document object
        """
        for key, value in self.header.items():
            for i, j in enumerate(value):
                print(f"[{key:{self.header_length}} {i+1:02}]: {j}")

    def __str__(self):  # pragma: no cover
        """
        Compiling a toString for a document
        """

        s = f"[DOCUMENT] {self.file}\n"

        for i, o in enumerate(self.all_peoplas):
            s += o.generate_summary(i+1) 

        for i, o in enumerate(self.all_peorels):
            s += o.generate_summary(i+1)
        
        for i, o in enumerate(self.all_action_groups):
            s += o.generate_summary(i+1)
        
        s += f"[DATAPOINTS] {len(self.data_points)} data points\n"

        s += "\n"
        s += str(self.data_points_df)

        return s

    def print_summary(self):  # pragma: no cover
        """
        Printing a summary of a document
        """

        logger.info(f"[DOCUMENT] {self.file}\n")

        # print(f"All Peoplas:")

        for i, p in enumerate(self.all_peoplas):
            logger.info( p.summarise(i) )

        # print("---------------------\n")
        # print(f"Current leaf Peoplas:")
        # logger.info(str(self.current_leaf_peopla))

        # print("---------------------\n")
        # print(f"All Peorels:")
        # for i, p in enumerate(self.all_peorels):
        #     logger.info(f"[{i}] " + str(p))

        # print("---------------------\n")
        # print(f"All ActionGroups:")
        # for i, p in enumerate(self.all_action_groups):
        #     logger.info(f"[{i}] " + str(p))

        # print("---------------------\n")
        # print(f"Found {len(self.data_points)} data points")
        # print(self.data_points_df)

    def get_header_information(self, flag):
        """
        Returning the value for a specific flag in a document header
        """
        return self.header[flag]


def extract_attribute_information(l0):
    """
    Parse details from an attribute line.
    Examples of attribute lines:
    - @[SCO, REN, LWH, Johnshill] (belongs to, e.g., OF)
    - :[1762-06] (belongs to, e.g., BORN)
    - :[1810-11->1818] (belongs to, e.g., EDUCATED)
    - :[1819-12->] (belongs to, e.g., HEALTH)
    - :[1820->]~ (belongs to, e.g., RESIDED)
    - CONDITION[Typhus fever] (belongs to, e.g., HEALTH)
    - ROLE[Clerk] (belongs to, e.g., OCC)
    - DUR[1 yr] (belongs to, e.g., OCC)
    """
    l1 = expand_attribute(l0)

    m = re.search(r"^(.*)\[(.*)\](~)?$", l1)

    key = translate_attribute(m.group(1))
    approx_flag = False if m.group(3) is None else True
    value = f"approx. {m.group(2)}" if approx_flag else m.group(2)

    return {key: value}


def expand_attribute(l):
    if l == "BIRTH":
        return "AGED[BIRTH]"
    elif l == "INF":
        return "AGED[INFANCY]"
    else:
        return l


### This is what we could do with Python 3.10
# def translate(x):
#     match x:
#         case ':':
#             return "DATE"
#         case '@':
#             return "AT"
#         case _:
#             return x
def translate_attribute(x):
    return {":": "DATE", "@": "AT",}.get(x, x)


def remove_all_leading_peopla_markup(l):
    """
    Removes markup, but retains the @ for place peoplas
    """
    return re.sub(r"^###[^@]*(\@?)(\[)", r"\1\2", l)


def remove_all_leading_action_markup(l):
    """
    Removes markup, but retains the @ for place peoplas
    """
    # return re.sub(r"^###\t(\S*)\t", "", l)

    return re.sub(r"^###[\t\S>]*(\t)+", "", l)


def remove_all_leading_pedigree_action_markup(l):
    """
    Removes markup, but retains the @ for place peoplas
    """
    # return re.sub(r"^###[\t\S\(>]*\t", "", l)
    return re.sub(r"^###[\t\S>]*(\t)+", "", l)


def remove_all_leading_relation_markup(l):
    """
    Removes markup
    """
    return re.sub(r"^###\t", "", l)


def extract_peopla_details(l0):
    """
    Parse details from a peopla line.
    Examples of peopla lines:
    - ###   [ADAM, Jean](5){80071ca9-d47a-4cb6-b283-f96ce7ad1618}
    - ###   [CRAWFURD, Andrew](x){5cf88045-6337-428c-ab5b-8ea9b1a50103}
    - ###   [M'TURK, Michael]
    - ###   [M'TURK, Michael]*
    - ###   @[SCO, REN, LWH, Johnshill]
    """

    l1 = remove_all_leading_peopla_markup(l0)

    m = re.search(peopla_regex, l1)

    place_flag = False if m.group(1) is None else True
    with_flag = False if m.group(2) is None else True
    content = m.group(3)
    local_id = None if m.group(4) is None else re.sub(r"[\(\)]", "", m.group(4))
    global_id = None if m.group(5) is None else re.sub(r"[\{\}]", "", m.group(5))
    inheritance_flag = False if m.group(6) is None else True

    logger.debug(
        f"New method for extracting peopla details:\n"
        + f" - is place flag present? '{place_flag}'\n"
        + f" - is a with flag present? '{with_flag}'\n"
        + f" - content is? '{content}'\n"
        + f" - local_id provided? '{local_id}'\n"
        + f" - global_id provided? '{global_id}'\n"
        + f" - inheritance flag provided? '{inheritance_flag}'"
    )

    peopla_info_dictionary = {
        "place_flag": place_flag,
        "with_flag": with_flag,
        "content": content,
        "local_id": local_id,
        "global_id": global_id,
        "inheritance_flag": inheritance_flag,
    }

    return peopla_info_dictionary


def extract_pedigree_action_details(l0):
    """
    Parse details from a relation line.
    Examples of action lines:
    """

    relation_depth = len(re.findall(peopla_relation_depth_regex, l0))

    l1 = remove_all_leading_pedigree_action_markup(l0).strip()

    m = re.search(action_regex, l1)
    action_text = m.group(1).rstrip()
    inheritance_flag = False if m.group(2) is None else True

    logger.debug(
        f"Method for extracting action details from pedigree:\n"
        + f" - pedigree depth is? '{relation_depth}'\n"
        + f" - attribute_text is ? '{action_text}'\n"
        + f" - inheritance flag provided? '{inheritance_flag}'"
    )

    pedigree_action_info_dictionary = {
        "pedigree_depth": relation_depth,
        "action_text": action_text,
        "inheritance_flag": inheritance_flag,
    }

    return pedigree_action_info_dictionary


def extract_relation_details(l0):
    """
    Parse details from a relation line.
    Examples of action lines:
    - ###	>	*SON*
    - ###	>	>	*DAUG*
    - ###	>	*FATHER*
    """

    l1 = remove_all_leading_relation_markup(l0)

    relation_depth = len(re.findall(peopla_relation_depth_regex, l1))

    m = re.search(peopla_relation_string_regex, l1)
    relation_text = m.group(1)

    logger.debug(
        f"Extracting relationship information:\n"
        + f" - relationship depth ? '{relation_depth}'\n"
        + f" - relationship text ? '{relation_text}'"
    )

    relationship_info_dictionary = {
        "relation_text": relation_text,
        "relation_depth": relation_depth,
    }

    return relationship_info_dictionary


def extract_action_details(l0):
    """
    Parse details from a action line.
    Examples of action lines:
    - ###	(	OF
    - ###       PROPRIETOR*

    """

    l1 = remove_all_leading_action_markup(l0)

    m = re.search(action_regex, l1)
    action_text = m.group(1).rstrip()
    inheritance_flag = False if m.group(2) is None else True

    logger.debug(
        f"New method for extracting action details:\n"
        + f" - attribute_text is ? '{action_text}'\n"
        + f" - inheritance flag provided? '{inheritance_flag}'"
    )

    action_info_dictionary = {
        "action_text": action_text,
        "inheritance_flag": inheritance_flag,
    }

    return action_info_dictionary


def is_action_group_directed(l0):
    if re.match(action_group_vs_regex, l0):
        return True
    elif re.match(action_group_w_regex, l0):
        return False
    else:
        return None


relation_gender_mapping = {
    "DAUG": "FEMALE",
    "MOTHER": "FEMALE",
    "SON": "MALE",
    "FATHER": "MALE",
}


def gender_inference_from_relation(t):
    inferred_gender = "UNKNOWN"
    if t in relation_gender_mapping:
        inferred_gender = relation_gender_mapping[t]
    return inferred_gender


def record_evidence(object, line_number):
    existing_list = object.evidence_reference
    existing_list.append(line_number)
    object.evidence_reference = sorted(set(existing_list))
    ### This is included so that we can use this function in testing
    ### We don't catch this output normally
    return object


def record_evidence_for_testing(object, line_number):
    existing_list = object.evidence_reference
    existing_list.append(line_number)
    object.evidence_reference = sorted(set(existing_list))
    return object


def update_breadcrumbs(existing_list, update_depth, update_object, label=""):
    if label != "":
        label += " "

    logger.debug(f"[Updating {label}breadcrumbs] The update depth is {update_depth}")
    logger.debug(f"[Updating {label}breadcrumbs] ...from {len(existing_list)} items)\n")

    # Remove everything including the level that is to be updated
    new_list = existing_list[:(update_depth)]

    # If you are updating something at a deeper level and you don't have an
    # entry for a higher level, need to add a None to show that that was missing
    # (this can happen where there isn't a Target peopla at a higher level (see
    # nested_pedictree_A3.txt).
    if update_depth > (len(new_list)):
        new_list = pad_with_none(new_list, update_depth)

    # Append the new object (this will be at the correct depth)
    new_list.append(update_object)

    logger.debug(f"[Updating {label}breadcrumbs] ...to {len(new_list)} items\n")

    return new_list


def pad_with_none(l, n, pad=None):
    if len(l) >= n:
        return l[:n]
    return l + ([pad] * (n - len(l)))


def get_pedigree_depth(l):
    return len(re.findall(peopla_relation_depth_regex, l))


def count_indent(l):
    return Counter(l)["\t"]


def obtain_and_remove_scope(l0):
    """
    Find out what the scope is and then remove it
    """

    basic_markup_regex = "^###\t"
    basic_scope_regex = r"\("
    leading_markup_regex = r"^(###[\(\t>]*)(.*)$"

    l1 = l0
    scope = None

    if re.search(basic_markup_regex, l0):

        m = re.search(leading_markup_regex, l0)
        leading_markup_text = m.group(1)
        trailing_content_text = m.group(2)

        if re.search(basic_scope_regex, leading_markup_text):
            scope = "leaf"
        else:
            scope = "full"

        unscoped_leading_markup_text = re.sub(
            basic_scope_regex, "", leading_markup_text
        )

        l1 = unscoped_leading_markup_text + trailing_content_text

    return [l1, scope]


def merge_attributes(existing_dict, new_dict):

    all_keys = sorted(set(list(existing_dict.keys()) + list(new_dict.keys())))

    merged_dict = {}

    for k in all_keys:
        merged_v = []
        if k in existing_dict:
            merged_v.append(existing_dict[k])
        if k in new_dict:
            merged_v.append(new_dict[k])

        if any(isinstance(v, list) for v in merged_v):
            merged_v = flatten(merged_v)

        merged_dict[k] = sorted(set(merged_v))

    # https://stackoverflow.com/questions/26910708/merging-dictionary-value-lists-in-python
    # merged_dict = {k: v + new_dict[k] for k, v in existing_dict.items()}

    return merged_dict


# Recursive function to flatten list
def flatten(a):
    res = []
    for x in a:
        if isinstance(x, list):
            res.extend(flatten(x))  # Recursively flatten nested lists
        else:
            res.append(x)  # Append individual elements
    return res


def build_map(l_in):
    ### Note that shortcut definitions can look like action/attributes
    ### so context is very important
    ### Note that attributes of actions can look like Peopla (e.g., @[S])
    ### in the following:
    ### ...
    ###	>	[C](1)
    ###	>	vs[D]
    ###	>		X
    ###	>			:[1800-02-02]
    ###	>			@[S2]
    ### ...
    ### so context is very important

    l = l_in.strip()

    parse_map = {}

    empty_rg = r"^\s*$"
    ignore_rg = r"^!.*$"
    header_rg = r"^##\w+:.*$"
    content_rg = r"^###\t"

    print(f"l: '{l}'\n")

    parse_map["empty"] = True if re.search(empty_rg, l) else False
    parse_map["ignore"] = True if re.search(ignore_rg, l) else False
    parse_map["header"] = True if re.search(header_rg, l) else False
    parse_map["content"] = True if re.search(content_rg, l) else False

    all_leading_markup_rg = r"^###[\t\S>]*(\t)+"

    shortcut_rg = r"^\^\d+:$"
    shortcut_def_rg = r"^[^\*\[\]\{\}\^]+\*?$"
    peopla_rg = r"^@?\[.*\](\(.*\))?(\{.*\})?$"
    relation_rg = r"^\*(.*)\*$"
    action_group_rg = r"^(vs|w/).*$"

    relation_depth_rg = r">\t"
    tab_rg = r"\t"

    if parse_map["content"]:

        l_partial_markup_removal = re.sub(content_rg, "", l)
        l_full_markup_removal = re.sub(all_leading_markup_rg, "", l)
        # print(f"l partial markup removal: '{l_partial_markup_removal}'\n")
        # print(f"l full markup removal: '{l_full_markup_removal}'\n")

        parse_map["shortcut"] = (
            True if re.search(shortcut_rg, l_full_markup_removal) else False
        )
        parse_map["shortcut_def"] = (
            True if re.search(shortcut_def_rg, l_full_markup_removal) else False
        )
        parse_map["peopla"] = (
            True if re.search(peopla_rg, l_full_markup_removal) else False
        )
        parse_map["relation"] = (
            True if re.search(relation_rg, l_full_markup_removal) else False
        )
        parse_map["action_group"] = (
            True if re.search(action_group_rg, l_full_markup_removal) else False
        )

        parse_map["indent_count"] = len(
            re.findall(relation_depth_rg, l_partial_markup_removal)
        )
        parse_map["tab_count"] = len(re.findall(tab_rg, l_partial_markup_removal))

    return parse_map
