import sys
import pytest
from pandas import testing

# import pandas as pd
# import tempfile
# import inspect
# import string
# import re

sys.path.append("src/ontologise")

from utils import (
    Peopla,
    ActionGroup,
    Peorel,
    extract_peopla_details,
    translate_attribute,
    extract_attribute_information,
    remove_all_leading_relation_markup,
    extract_relation_details,
    remove_all_leading_peopla_markup,
    remove_all_leading_action_markup,
    remove_all_leading_pedigree_action_markup,
    extract_action_details,
    extract_pedigree_action_details,
    is_action_group_directed,
    gender_inference_from_relation,
    update_breadcrumbs,
    pad_with_none,
    get_pedigree_depth,
    count_indent,
    obtain_and_remove_scope,
    merge_attributes,
    flatten,
    build_map,
)


@pytest.mark.parametrize(
    "s_in, s_out_expected",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the scope as expected
    [
        # TEST: Basic
        ("###	vs[A]", True),
        ("###	w/[A]", False),
        ("###	a[A]", None),
    ],
)
def test_is_action_group_directed(s_in, s_out_expected):
    s_out_observed = is_action_group_directed(s_in)
    assert s_out_observed == s_out_expected


def generate_action_or_attribute_build_map(
    indent_val=0, tab_val=0, peopla_val=False, shortcut_def_val=False
):
    return {
        "empty": False,
        "ignore": False,
        "header": False,
        "content": True,
        "shortcut": False,
        # Actions/attributes have the same format as a
        # shortcut definition, only the context will tell us
        # the difference, so we need a way to pass this information
        # to this dictionary for testing
        "shortcut_def": shortcut_def_val,
        # Actions/attributes can have the same format as a
        # Peopla definition, only the context will tell us
        # the difference, so we need a way to pass this information
        # to this dictionary for testing
        "peopla": peopla_val,
        "relation": False,
        "action_group": False,
        "indent_count": indent_val,
        "tab_count": tab_val,
    }


@pytest.mark.parametrize(
    "s,map_expected",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the content map as expected
    [
        # --- THINGS TO IGNORE --------------------------------------
        # TEST: Empty (no text)
        ("", {"empty": True, "ignore": False, "header": False, "content": False,},),
        # TEST: Empty (tab)
        ("	", {"empty": True, "ignore": False, "header": False, "content": False,},),
        # TEST: ignore (via !)
        ("! X", {"empty": False, "ignore": True, "header": False, "content": False,},),
        # TEST: ignore (via !) with following ###
        (
            "! ### [X]",
            {"empty": False, "ignore": True, "header": False, "content": False,},
        ),
        # TEST: markup separator - all values false
        (
            "------------",
            {"empty": False, "ignore": False, "header": False, "content": False,},
        ),
        # TEST: markup separator - all values false
        (
            "------------",
            {"empty": False, "ignore": False, "header": False, "content": False,},
        ),
        # --- THINGS TO PARSE ---------------------------------------
        # Header text
        (
            "##X:	Y",
            {"empty": False, "ignore": False, "header": True, "content": False,},
        ),
        # Shortcut
        (
            "###		^1:",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": True,
                "shortcut_def": False,
                "peopla": False,
                "relation": False,
                "action_group": False,
                "indent_count": 0,
                "tab_count": 1,
            },
        ),
        # Shortcut definition - without !
        (
            "###		X*",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": True,
                "peopla": False,
                "relation": False,
                "action_group": False,
                "indent_count": 0,
                "tab_count": 1,
            },
        ),
        # Shortcut definition - with !
        (
            "###		!X",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": True,
                "peopla": False,
                "relation": False,
                "action_group": False,
                "indent_count": 0,
                "tab_count": 1,
            },
        ),
        # Peopla - person
        (
            "###	[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 0,
                "tab_count": 0,
            },
        ),
        # Peopla - person with 1 tab
        (
            "###		[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 0,
                "tab_count": 1,
            },
        ),
        # Peopla - person with tabs
        (
            "###	>	[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 1,
                "tab_count": 1,
            },
        ),
        # Peopla - person with tabs
        (
            "###	>		[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 1,
                "tab_count": 2,
            },
        ),
        # Peopla - person with tabs
        (
            "###	>	>	[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 2,
                "tab_count": 2,
            },
        ),
        # Peopla - person with tabs
        (
            "###	(>	[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 1,
                "tab_count": 1,
            },
        ),
        # Peopla - person with tabs
        (
            "###	(>		[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 1,
                "tab_count": 2,
            },
        ),
        # Peopla - person with tabs and scope
        (
            "###	(>	>	[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 2,
                "tab_count": 2,
            },
        ),
        # Peopla: place
        (
            "###	@[X]",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": True,
                "relation": False,
                "action_group": False,
                "indent_count": 0,
                "tab_count": 0,
            },
        ),
        # Relation
        (
            "###	*X*",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": False,
                "relation": True,
                "action_group": False,
                "indent_count": 0,
                "tab_count": 0,
            },
        ),
        # Action Group
        (
            "###	vs[X](i-1){j-1}",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": False,
                "relation": False,
                "action_group": True,
                "indent_count": 0,
                "tab_count": 0,
            },
        ),
        # Action Group
        (
            "###	w/[X](i-1){j-1}",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": False,
                "relation": False,
                "action_group": True,
                "indent_count": 0,
                "tab_count": 0,
            },
        ),
        # Action Group
        (
            "###	>	w/[X](i-1){j-1}",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": False,
                "relation": False,
                "action_group": True,
                "indent_count": 1,
                "tab_count": 1,
            },
        ),
        # Action Group
        (
            "###	>		w/[X](i-1){j-1}",
            {
                "empty": False,
                "ignore": False,
                "header": False,
                "content": True,
                "shortcut": False,
                "shortcut_def": False,
                "peopla": False,
                "relation": False,
                "action_group": True,
                "indent_count": 1,
                "tab_count": 2,
            },
        ),
        # An action or an attribute line
        # (this could also be interpreted as a shortcut
        # definition line, only the context will tell us
        # which one it is)
        (
            "###	>		X",
            generate_action_or_attribute_build_map(1, 2, shortcut_def_val=True),
        ),
        # An action or an attribute line
        ("###	>			:[YYYY-MM-DD]", generate_action_or_attribute_build_map(1, 3),),
        # An action or an attribute line
        ("###	>	>		:[YYYY-MM-DD]", generate_action_or_attribute_build_map(2, 3),),
        # An action or an attribute line
        (
            "###	>			@[Y]",
            generate_action_or_attribute_build_map(1, 3, peopla_val=True),
        ),
    ],
)
def test_build_map(s, map_expected):
    map_observed = build_map(s)
    assert map_observed == map_expected


@pytest.mark.parametrize(
    "s,s_dict_expected",
    # parameters are:
    # (1) the attribute string (with leading ### and white space removed)
    # (2) the dictionary created from that string
    # - @[SCO, REN, LWH, Johnshill] (belongs to, e.g., OF)
    # - :[1762-06] (belongs to, e.g., BORN)
    # - :[1810-11->1818] (belongs to, e.g., EDUCATED)
    # - :[1819-12->] (belongs to, e.g., HEALTH)
    # - :[1820->]~ (belongs to, e.g., RESIDED)
    # - CONDITION[Typhus fever] (belongs to, e.g., HEALTH)
    # - ROLE[Clerk] (belongs to, e.g., OCC)
    # - DUR[1 yr] (belongs to, e.g., OCC)
    [
        # TEST:
        ("A", {"action_text": "A", "inheritance_flag": False}),
        ("A*", {"action_text": "A", "inheritance_flag": True}),
    ],
)
def test_extract_action_details(s, s_dict_expected):
    s_dict_observed = extract_action_details(s)
    assert s_dict_observed == s_dict_expected


@pytest.mark.parametrize(
    "s,s_dict_expected",
    # parameters are:
    # (1) the attribute string (with leading ### and white space removed)
    # (2) the dictionary created from that string
    # - @[SCO, REN, LWH, Johnshill] (belongs to, e.g., OF)
    # - :[1762-06] (belongs to, e.g., BORN)
    # - :[1810-11->1818] (belongs to, e.g., EDUCATED)
    # - :[1819-12->] (belongs to, e.g., HEALTH)
    # - :[1820->]~ (belongs to, e.g., RESIDED)
    # - CONDITION[Typhus fever] (belongs to, e.g., HEALTH)
    # - ROLE[Clerk] (belongs to, e.g., OCC)
    # - DUR[1 yr] (belongs to, e.g., OCC)
    [
        # TEST:
        (
            "###	>		E",
            {"pedigree_depth": 1, "action_text": "E", "inheritance_flag": False},
        ),
        (
            "###	>		E*",
            {"pedigree_depth": 1, "action_text": "E", "inheritance_flag": True},
        ),
    ],
)
def test_extract_pedigree_action_details(s, s_dict_expected):
    s_dict_observed = extract_pedigree_action_details(s)
    assert s_dict_observed == s_dict_expected


@pytest.mark.parametrize(
    "s_in, s_out_expected",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    [
        # TEST: Basic
        ("###	(	X", "X"),
        ("###		X", "X"),
        ("###	>	(	X", "X"),
        ("###	>	>		X", "X"),
        ("###	>	(>		X", "X"),
        ("###	(	@X", "@X"),
        ("###		@X", "@X"),
        ("###	>	(	@X", "@X"),
        ("###	>	>		@X", "@X"),
        ("###	>	(>		@X", "@X"),
    ],
)
def test_remove_all_leading_action_markup(s_in, s_out_expected):
    s_out_observed = remove_all_leading_action_markup(s_in)
    assert s_out_observed == s_out_expected


@pytest.mark.parametrize(
    "s_in, s_out_expected",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    [
        # TEST: Basic
        ("###	>	*A*", ">	*A*"),
        ("###	>	>	*A*", ">	>	*A*"),
    ],
)
def test_remove_all_leading_relation_markup(s_in, s_out_expected):
    s_out_observed = remove_all_leading_relation_markup(s_in)
    assert s_out_observed == s_out_expected


@pytest.mark.parametrize(
    "s_in, s_out_expected",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    [
        # TEST: Basic
        ("###	[A, B]", "[A, B]"),
        ("###	[A, B](n){i-0}", "[A, B](n){i-0}"),
        ("###	[M'A, B]", "[M'A, B]"),
        ("###	vs[A, B]", "[A, B]"),
        ("###	w/[A, B]", "[A, B]"),
        ("###	(>	[A, B]", "[A, B]"),
        ("###	>	[A, B]", "[A, B]"),
        ("###	>	>	[A, B]", "[A, B]"),
        ("###	@[C, D]", "@[C, D]"),
    ],
)
def test_remove_all_leading_peopla_markup(s_in, s_out_expected):
    s_out_observed = remove_all_leading_peopla_markup(s_in)
    assert s_out_observed == s_out_expected


@pytest.mark.parametrize(
    "s_in, s_out_expected",
    # parameters are:
    # (1) the attribute tag/symbol in
    # (2) the expected tag/symbol out (as to be used in a dictionary)
    [
        # TEST: Basic
        (":", "DATE"),
        ("@", "AT"),
        ("X", "X"),
    ],
)
def test_translate_attribute(s_in, s_out_expected):
    s_out_observed = translate_attribute(s_in)
    assert s_out_observed == s_out_expected


@pytest.mark.parametrize(
    "s,s_dict_expected",
    # parameters are:
    # (1) the attribute string (with leading ### and white space removed)
    # (2) the dictionary created from that string
    # - @[SCO, REN, LWH, Johnshill] (belongs to, e.g., OF)
    # - :[1762-06] (belongs to, e.g., BORN)
    # - :[1810-11->1818] (belongs to, e.g., EDUCATED)
    # - :[1819-12->] (belongs to, e.g., HEALTH)
    # - :[1820->]~ (belongs to, e.g., RESIDED)
    # - CONDITION[Typhus fever] (belongs to, e.g., HEALTH)
    # - ROLE[Clerk] (belongs to, e.g., OCC)
    # - DUR[1 yr] (belongs to, e.g., OCC)
    [
        # TEST: @ symbol
        ("@[P]", {"AT": "P"}),
        # TEST: : date
        (":[YYYY-MM]", {"DATE": "YYYY-MM"}),
        # TEST: approximate : date
        (":[YYYY-MM]~", {"DATE": "approx. YYYY-MM"}),
        # TEST: all other attributes
        ("A[B]", {"A": "B"}),
    ],
)
def test_extract_attribute_information(s, s_dict_expected):
    s_dict_observed = extract_attribute_information(s)
    assert s_dict_observed == s_dict_expected


@pytest.mark.parametrize(
    "s,s_dict_expected",
    # parameters are:
    # (1) the relation string (SON/DAUG/FATHER/MOTHER)
    # (2) the relation depth
    [
        # TEST:
        (">	*X*", {"relation_text": "X", "relation_depth": 1}),
        # TEST:
        (">	>	*Y*", {"relation_text": "Y", "relation_depth": 2}),
        # TEST:
        (">	>	>	*Z*", {"relation_text": "Z", "relation_depth": 3}),
    ],
)
def test_extract_relation_details(s, s_dict_expected):
    s_dict_observed = extract_relation_details(s)
    assert s_dict_observed == s_dict_expected


@pytest.mark.parametrize(
    "s,s_dict_expected",
    # parameters are:
    # (1) the peopla string (with leading ### and white space removed)
    # (2) the parsed values from that string
    [
        # TEST: Basic
        (
            "###	[Surname, First]",
            {
                "place_flag": False,
                "with_flag": False,
                "content": "Surname, First",
                "local_id": None,
                "global_id": None,
                "inheritance_flag": False,
            },
        ),
        # TEST: Basic with local ID
        (
            "###	[Surname, First](local-id)",
            {
                "place_flag": False,
                "with_flag": False,
                "content": "Surname, First",
                "local_id": "local-id",
                "global_id": None,
                "inheritance_flag": False,
            },
        ),
        # TEST: Basic with global ID
        (
            "###	[Surname, First]{global-id}",
            {
                "place_flag": False,
                "with_flag": False,
                "content": "Surname, First",
                "local_id": None,
                "global_id": "global-id",
                "inheritance_flag": False,
            },
        ),
        # TEST: Basic with inheritance
        (
            "###	[Surname, First]*",
            {
                "place_flag": False,
                "with_flag": False,
                "content": "Surname, First",
                "local_id": None,
                "global_id": None,
                "inheritance_flag": True,
            },
        ),
        # TEST: Basic with local and global IDs
        (
            "###	[Surname, First](local-id){global-id}",
            {
                "place_flag": False,
                "with_flag": False,
                "content": "Surname, First",
                "local_id": "local-id",
                "global_id": "global-id",
                "inheritance_flag": False,
            },
        ),
        # TEST: includes @ flag
        (
            "###	@[Place, A](local-id){global-id}",
            {
                "place_flag": True,
                "with_flag": False,
                "content": "Place, A",
                "local_id": "local-id",
                "global_id": "global-id",
                "inheritance_flag": False,
            },
        ),
    ],
)
def test_extract_peopla_details(s, s_dict_expected):
    s_dict_observed = extract_peopla_details(s)
    assert s_dict_observed == s_dict_expected


@pytest.mark.parametrize(
    "relation,gender_expected",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    [
        # TEST: Basic
        ("DAUG", "FEMALE"),
        ("MOTHER", "FEMALE"),
        ("SON", "MALE"),
        ("FATHER", "MALE"),
        ("X", "UNKNOWN"),
    ],
)
def test_gender_inference_from_relation(relation, gender_expected):
    gender_observed = gender_inference_from_relation(relation)
    assert gender_observed == gender_expected


@pytest.mark.parametrize(
    "input_list,update_depth,update_object,expected_output",
    # parameters are:
    # (1) an input list
    # (2) the level at which to update
    # (3) what to update this level with
    # (4) the expected result
    [
        # TEST: Basic
        ([], 0, "A", ["A"]),
        (["B"], 0, "A", ["A"]),
        (["B", "C"], 0, "A", ["A"]),
        (["A"], 1, "B", ["A", "B"]),
        (["A", "B"], 1, "C", ["A", "C"]),
        (["A", "B", "C", "D"], 1, "C", ["A", "C"]),
        ([], 1, "A", [None, "A"]),
        ([], 2, "A", [None, None, "A"]),
        (["A", None], 2, "B", ["A", None, "B"]),
    ],
)
def test_breadcrumb_updates(input_list, update_depth, update_object, expected_output):
    observed_output = update_breadcrumbs(input_list, update_depth, update_object)
    assert observed_output == expected_output


@pytest.mark.parametrize(
    "input_list,target_length,expected_output",
    # parameters are:
    # (1) an input list
    # (2) the level at which to update
    # (3) what to update this level with
    # (4) the expected result
    [
        # TEST: Basic
        ([], 1, [None]),
        ([None], 2, [None, None]),
        (["A"], 1, ["A"]),
        (["A"], 2, ["A", None]),
    ],
)
def test_pad_with_none(input_list, target_length, expected_output):
    observed_output = pad_with_none(input_list, target_length)
    assert observed_output == expected_output


@pytest.mark.parametrize(
    "input_line,expected_depth",
    # parameters are:
    # (1) an input list
    # (2) the level at which to update
    # (3) what to update this level with
    # (4) the expected result
    [
        # TEST: Basic
        ("###	[X]", 0),
        ("###	>	[X]", 1),
        ("###	>	>	[X]", 2),
        ("###	(>	[X]", 1),
        ("###	(>	>	[X]", 2),
        ("###	>	[>]", 1),
    ],
)
def test_get_pedigree_depth(input_line, expected_depth):
    observed_depth = get_pedigree_depth(input_line)
    assert observed_depth == expected_depth


@pytest.mark.parametrize(
    "input_line,expected_indent",
    # parameters are:
    # (1) an input list
    # (2) the level at which to update
    # (3) what to update this level with
    # (4) the expected result
    [
        # TEST: Basic
        ("###		[X]", 2),
        ("###	>	[X]", 2),
        ("###			[X]", 3),
        ("###	>		[X]", 3),
        ("###	>	>	[X]", 3),
        ("###	(	[X]", 2),
        ("###	(>	[X]", 2),
        ("###	(	(	[X]", 3),
        ("###	(>		[X]", 3),
        ("###	(>	(>	[X]", 3),
    ],
)
def test_count_indent(input_line, expected_indent):
    observed_indent = count_indent(input_line)
    assert observed_indent == expected_indent


@pytest.mark.parametrize(
    "s_in, s_out_expected",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    [
        # TEST: Basic
        ("###	>		E", "E"),
        ("###	>	>		E", "E"),
    ],
)
def test_remove_all_leading_pedigree_action_markup(s_in, s_out_expected):
    s_out_observed = remove_all_leading_pedigree_action_markup(s_in)
    assert s_out_observed == s_out_expected


@pytest.mark.parametrize(
    "s_in, expected_s_out, expected_scope",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    # (3) the scope (leaf/full) as assessed by the presence/absence of (
    [
        # TEST: Basic
        ("###	X", "###	X", "full"),
        ("###	>	X", "###	>	X", "full"),
        ("###	(>	X", "###	>	X", "leaf"),
        ("###	>	>	X", "###	>	>	X", "full"),
        ("###	(>	>	X", "###	>	>	X", "leaf"),
        ("###	[X]", "###	[X]", "full"),
        ("###	>	[X]", "###	>	[X]", "full"),
        ("###	(>	[X]", "###	>	[X]", "leaf"),
        ("###	>	>	[X]", "###	>	>	[X]", "full"),
        ("###	(>	>	[X]", "###	>	>	[X]", "leaf"),
        ("###	@X", "###	@X", "full"),
        ("###	>	@X", "###	>	@X", "full"),
        ("###	(>	@X", "###	>	@X", "leaf"),
        ("###	>	>	@X", "###	>	>	@X", "full"),
        ("###	(>	>	@X", "###	>	>	@X", "leaf"),
        ### If it's a line that contains a local ID, make sure that we're
        ### not losing that information - only remove (s when they
        ### are in the leading markup
        ("###	X(i-1)", "###	X(i-1)", "full"),
        ("###	[X](i-1)", "###	[X](i-1)", "full"),
        ("###	@X(i-1)", "###	@X(i-1)", "full"),
        ("###	(	X(i-1)", "###		X(i-1)", "leaf"),
        ("###	(	[X](i-1)", "###		[X](i-1)", "leaf"),
        ("###	(	@X(i-1)", "###		@X(i-1)", "leaf"),
        ### If it's a line that doesn't start with ###, send it back
        ### unaltered with scope set to None
        ("TEST", "TEST", None),
        ("##    X", "##    X", None),
        ("", "", None),
        ("!", "!", None),
    ],
)
def test_obtain_and_remove_scope(s_in, expected_s_out, expected_scope):
    s_out = obtain_and_remove_scope(s_in)
    assert s_out[0] == expected_s_out
    assert s_out[1] == expected_scope


@pytest.mark.parametrize(
    "existing_dict, new_dict, expected_output",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    # (3) the scope (leaf/full) as assessed by the presence/absence of (
    [
        # TEST: Basic, with numbers
        ({"A": 1}, {"A": 1}, {"A": [1]}),
        ({"A": 1}, {"A": 2}, {"A": [1, 2]}),
        ({"A": [1]}, {"A": [2]}, {"A": [1, 2]}),
        ({"A": 1}, {"A": 2, "B": 3}, {"A": [1, 2], "B": [3]}),
        ({"A": 1}, {"B": 3}, {"A": [1], "B": [3]}),
        ({}, {"A": 1}, {"A": [1]}),
        ({"A": 1}, {}, {"A": [1]}),
        ({"A": [1, 2]}, {"A": 3}, {"A": [1, 2, 3]}),
        ({"A": [1, 2]}, {"A": [3]}, {"A": [1, 2, 3]}),
        ({"A": [1, 2]}, {"B": 3}, {"A": [1, 2], "B": [3]}),
        ({"A": [1, 2]}, {"B": [3]}, {"A": [1, 2], "B": [3]}),
    ],
)
def test_merge_attributes(existing_dict, new_dict, expected_output):
    s_out = merge_attributes(existing_dict, new_dict)
    assert s_out == expected_output


@pytest.mark.parametrize(
    "list_in, expected_output",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    # (3) the scope (leaf/full) as assessed by the presence/absence of (
    [
        # TEST: Basic, with numbers
        ([1], [1]),
        ([[1]], [1]),
        ([[1, 2]], [1, 2]),
        ([[1, 2], 3], [1, 2, 3]),
    ],
)
def test_flatten(list_in, expected_output):
    s_out = flatten(list_in)
    assert s_out == expected_output


@pytest.mark.parametrize(
    "peopla1, peopla2, expected_result",
    # parameters are:
    # (1) the line as read in the Document
    # (2) the line as expected following markup removal
    # (3) the scope (leaf/full) as assessed by the presence/absence of (
    [
        # TEST:
        (Peopla("A"), Peopla("A"), True),
        (Peopla("A"), Peopla("B"), False),
        (Peopla("A", local_id="i"), Peopla("A", local_id="i"), True),
        (Peopla("A", global_id="i"), Peopla("A", local_id="i"), False),
    ],
)
def test_peopla_equality(peopla1, peopla2, expected_result):
    # parameters are:
    # (1) the first peopla
    # (2) the second peopla
    # (3) whether we expect them to match (True/False)
    observed_result = peopla1.peopla_match(peopla2)
    assert observed_result == expected_result


@pytest.mark.parametrize(
    "object1, object2, expected_result",
    # parameters are:
    # (1) the first object
    # (2) the second object
    # (3) whether we expect them to match (True/False)
    [
        # TEST:
        (
            Peorel(Peopla("B"), Peopla("A"), "SON", 1),
            Peorel(Peopla("B"), Peopla("A"), "SON", 1),
            True,
        ),
        # TEST:
        (
            Peorel(Peopla("B"), Peopla("A"), "SON", 1),
            Peorel(Peopla("B"), Peopla("A"), "DAUG", 1),
            False,
        ),
        # TEST: ActionGroup with different direction
        (
            ActionGroup(
                type="X",
                directed=False,
                source_peopla=Peopla("C"),
                target_peoplas=[Peopla("D")],
            ),
            ActionGroup(
                type="X",
                directed=True,
                source_peopla=Peopla("C"),
                target_peoplas=[Peopla("D")],
            ),
            False,
        ),
        # TEST: ActionGroup with different length of target Peoplas (1/2)
        (
            ActionGroup(
                type="X",
                directed=False,
                source_peopla=Peopla("C"),
                target_peoplas=[Peopla("D")],
            ),
            ActionGroup(
                type="X",
                directed=False,
                source_peopla=Peopla("C"),
                target_peoplas=[Peopla("D"), Peopla("E")],
            ),
            False,
        ),
        # TEST: ActionGroup with different length of target Peoplas (0/1)
        (
            ActionGroup(
                type="X",
                directed=False,
                source_peopla=Peopla("C"),
                target_peoplas=[Peopla("D")],
            ),
            ActionGroup(
                type="X", directed=False, source_peopla=Peopla("C"), target_peoplas=[],
            ),
            False,
        ),
        # TEST: ActionGroup with different target Peoplas (by local_id)
        (
            ActionGroup(
                type="X",
                directed=False,
                source_peopla=Peopla("C"),
                target_peoplas=[Peopla("D")],
            ),
            ActionGroup(
                type="X",
                directed=False,
                source_peopla=Peopla("C"),
                target_peoplas=[Peopla("D", local_id="x")],
            ),
            False,
        ),
    ],
)
def test_object_equality(object1, object2, expected_result):
    observed_result = object1 == object2
    assert observed_result == expected_result
