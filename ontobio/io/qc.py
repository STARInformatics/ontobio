import json
import enum
import collections
import datetime

from typing import List, Dict, Any, Tuple
from ontobio import ontol
from ontobio import ecomap
from ontobio.io import assocparser
from ontobio.io import gaference

FailMode = enum.Enum("FailMode", {"SOFT": "soft", "HARD": "hard"})
ResultType = enum.Enum("Result", {"PASS": "Pass", "WARNING": "Warning", "ERROR": "Error"})
RepairState = enum.Enum("RepairState", {"OKAY": "Okay", "REPAIRED": "Repaired", "FAILED": "Failed"})

# TestResult = collections.namedtuple("TestResult", ["result_type", "message", "result"])
class TestResult(object):
    def __init__(self, result_type: ResultType, message: str, result: List):
        self.result_type = result_type
        self.message = message
        self.result = result

"""
Send True for passes, and this returns the PASS ResultType, and if False, then
depending on the fail mode it returns either WARNING or ERROR ResultType.
"""
def result(passes: bool, fail_mode: FailMode) -> ResultType:
    if passes:
        return ResultType.PASS

    # Else we didn't pass
    if fail_mode == FailMode.SOFT:
        return ResultType.WARNING

    if fail_mode == FailMode.HARD:
        return ResultType.ERROR

def repair_result(repair_state: RepairState, fail_mode: FailMode) -> ResultType:
    if repair_state == RepairState.OKAY:
        return ResultType.PASS

    if repair_state == RepairState.REPAIRED:
        return ResultType.WARNING

    return result(False, fail_mode)


class GoRule(object):

    def __init__(self, id, title, fail_mode: FailMode):
        self.id = id
        self.title = title
        self.fail_mode = fail_mode

    def _list_terms(self, pipe_separated):
        terms = pipe_separated.split("|")
        terms = [t for t in terms if t != ""] # Remove empty strings
        return terms

    def _result(self, passes: bool) -> TestResult:
        return TestResult(result(passes, self.fail_mode), self.title, passes)

    def run_test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        result = self.test(annotation, config)
        result.result = annotation
        return result

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        pass

class RepairRule(GoRule):

    def __init__(self, id, title, fail_mode):
        super().__init__(id, title, fail_mode)

    def message(self, state: RepairState) -> str:
        message = ""
        if state == RepairState.REPAIRED:
            message = "Found violation of: `{}` but was repaired".format(self.title)
        elif state == RepairState.FAILED:
            message = "Found violatoin of: `{}` and could not be repaired".format(self.title)

        return message

    def run_test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        return self.test(annotation, config)

    def repair(self, annotation: List) -> Tuple[List, RepairState]:
        pass


class GoRule02(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000002", "No 'NOT' annotations to 'protein binding ; GO:0005515'", FailMode.SOFT)


    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:

        qualifier = self._list_terms(annotation[3])
        goclass = annotation[4]

        fails = (goclass == "GO:0005515" and "NOT" in qualifier)
        return self._result(not fails)

class GoRule06(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000006", "IEP and HEP usage is restricted to terms from the Biological Process ontology", FailMode.HARD)

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:

        aspect = annotation[8]
        evidence = annotation[6]
        fails = evidence in ["IEP", "HEP"] and aspect != "P"
        return self._result(not fails)

class GoRule07(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000007", "IPI should not be used with catalytic activity molecular function terms", FailMode.SOFT)
        self.children_of_catalytic_activity = None

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        catalytic_activity = "GO:0003824"
        if config.ontology is not None and self.children_of_catalytic_activity is None:
            # We'll define children_of_catalytic_activity if we have an ontology *and* if we haven't defined it before already
            self.children_of_catalytic_activity = set(config.ontology.descendants(catalytic_activity, relations=["subClassOf"], reflexive=True))

        goterm = annotation[4]
        evidence = annotation[6]

        fails = False
        if self.children_of_catalytic_activity is not None:
            # We fail if evidence is IPI and the goterm is a subclass of catalytic activity, else we good
            fails = evidence == "IPI" and goterm in self.children_of_catalytic_activity

        return self._result(not fails)


class GoRule08(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000008", "No annotations should be made to uninformatively high level terms", FailMode.SOFT)
        self.do_not_annotate = None
        self.do_not_manually_annotate = None

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        # Cache the subsets
        if self.do_not_annotate is None and config.ontology is not None:
            self.do_not_annotate = set(config.ontology.extract_subset("gocheck_do_not_annotate"))
            self.do_not_manually_annotate = set(config.ontology.extract_subset("gocheck_do_not_manually_annotate"))
        elif self.do_not_annotate is None and config.ontology is None:
            self.do_not_annotate = []
            self.do_not_manually_annotate = []

        goid = annotation[4]
        evidence = annotation[6]

        auto_annotated = goid in self.do_not_annotate
        manually_annotated = evidence != "IEA" and goid in self.do_not_manually_annotate
        not_high_level = not (auto_annotated or manually_annotated)

        t = result(not_high_level, self.fail_mode)
        return TestResult(t, self.title, not_high_level)


class GoRule11(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000011", "ND annotations to root nodes only", FailMode.HARD)
        self.root_go_classes = ["GO:0003674", "GO:0005575", "GO:0008150"]

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        goclass = annotation[4]
        evidence = annotation[6]

        # If we see a bad evidence, and we're not in a paint file then fail.
        # We're good if both predicates are true, or neither are true
        success = (evidence == "ND" and goclass in self.root_go_classes) or (evidence != "ND" and goclass not in self.root_go_classes)
        return self._result(success)

class GoRule13(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000013", "Taxon-appropriate annotation check", FailMode.SOFT)

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        if config.annotation_inferences is None:
            # Auto pass if we don't have inferences
            return self._result(True)

        inference_results = gaference.produce_inferences(annotation, config.annotation_inferences) #type: List[gaference.InferenceResult]
        taxon_passing = True
        for result in inference_results:
            if result.problem == gaference.ProblemType.TAXON:
                taxon_passing = False
                break

        return self._result(taxon_passing)

class GoRule15(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000015", "Dual species taxon check", FailMode.SOFT)
        self.allowed_dual_species_terms = None

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:

        # Cache the allowed terms
        if self.allowed_dual_species_terms is None and config.ontology is not None:
            interaction_terms = config.ontology.descendants("GO:0044419", relations=["subClassOf"], reflexive=True)
            other_organism_terms = config.ontology.descendants("GO:0044215", relations=["subClassOf"], reflexive=True)
            self.allowed_dual_species_terms = set(interaction_terms + other_organism_terms)

        passes = False
        if self.allowed_dual_species_terms is not None:
            dual = len(self._list_terms(annotation[12])) == 2
            goterm = annotation[4]

            # We fail if we are a dual taxon and then the term is not in this list
            # This is the same as dual -> goterm in list
            # Implication rewritten is Not P OR Q
            passes = not dual or (goterm in self.allowed_dual_species_terms)

        return self._result(passes)


class GoRule16(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000016", "All IC annotations should include a GO ID in the \"With/From\" column", FailMode.HARD)

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        evidence = annotation[6]
        withfrom = self._list_terms(annotation[7])

        okay = True
        if evidence == "IC":
            only_go = [t for t in withfrom if t.startswith("GO:")] # Filter terms that aren't GO terms
            okay = len(only_go) >= 1

        return self._result(okay)


class GoRule17(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000017", "IDA annotations must not have a With/From entry", FailMode.SOFT)

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        evidence = annotation[6]
        withfrom = annotation[7]

        if evidence == "IDA":
            return self._result(not bool(withfrom))
        else:
            return self._result(True)

class GoRule18(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000018", "IPI annotations require a With/From entry", FailMode.SOFT)

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        evidence = annotation[6]
        withfrom = annotation[7]

        if evidence == "IPI":
            return self._result(bool(withfrom))
        else:
            return self._result(True)


class GoRule26(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000026", "IBA evidence codes should be filtered from main MOD gaf sources", FailMode.HARD)
        self.offending_evidence = ["IBA"]

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        evidence = annotation[6]
        # If we see a bad evidence, and we're not in a paint file then fail.
        fails = (evidence in self.offending_evidence and not config.paint)
        return self._result(not fails)

class GoRule28(RepairRule):
    def __init__(self):
        super().__init__("GORULE:0000028", "Aspect can only be one of C, P, F", FailMode.HARD)
        self.namespace_aspect_map = {
            "biological_process": "P",
            "cellular_component": "C",
            "molecular_function": "F"
        }

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        aspect = annotation[8].upper()
        goterm = annotation[4]

        if config.ontology is None:
            return TestResult(ResultType.PASS, self.title, annotation)

        namespaces = [predval for predval in config.ontology.get_graph().node.get(goterm, {}).get("meta", {}).get("basicPropertyValues", []) if predval["pred"]=="OIO:hasOBONamespace"]
        # the namespaces expression cascades through the json representation of this
        # ontology using empty dict/list if the key is not present

        if len(namespaces) == 0:
            # If this doesn't exist, then it's fine
            return TestResult(ResultType.PASS, self.title, annotation)

        namespace = namespaces[0]["val"]
        expected_aspect = self.namespace_aspect_map[namespace]

        correct_aspect = expected_aspect == aspect
        annotation[8] = expected_aspect

        repair_state = None
        if correct_aspect:
            repair_state = RepairState.OKAY
        else:
            repair_state = RepairState.REPAIRED

        return TestResult(repair_result(repair_state, self.fail_mode), self.message(repair_state), annotation)


class GoRule29(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000029", "All IEAs over a year old are removed", FailMode.HARD)
        self.one_year = datetime.timedelta(days=365)

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        evidence = annotation[6]
        date = annotation[13]

        now = datetime.datetime.today()

        fails = (evidence == "IEA" and now - datetime.datetime(int(date[0:4]), int(date[4:6]), int(date[6:8]), 0, 0, 0, 0) > self.one_year)
        return self._result(not fails)


class GoRule30(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000030", "Deprecated GO_REFs are not allowed", FailMode.HARD)
        
    def _ref_curi_to_id(self, goref) -> str:
        """
        Changes reference IDs in the form of GO_REF:nnnnnnn to goref-nnnnnnn
        """
        return goref.lower().replace("_", "").replace(":", "-")

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        references = self._list_terms(annotation[5])
        for ref in references:
            # Not allowed is obsolete and GO_PAINT:x
            if ref.startswith("GO_PAINT") or (config.goref_metadata is not None and config.goref_metadata.get(self._ref_curi_to_id(ref), {}).get("is_obsolete", False)):
                return self._result(False)
            
        return self._result(True)

class GoRule37(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000037", "IBA annotations should ONLY be assigned_by GO_Central and have PMID:21873635 as a reference", FailMode.HARD)

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        # If the evidence code is IBA, then (1) the assigned_by field must be GO_Central and (2) the reference field must be PMID:21873635
        evidence = annotation[6]
        references = self._list_terms(annotation[5])
        assigned_by = annotation[14]

        result = self._result(True) # By default we pass
        if evidence == "IBA":
            result = self._result(assigned_by == "GO_Central" and "PMID:21873635" in references)

        return result
        
class GoRule39(GoRule):
    
    def __init__(self):
        super().__init__("GORULE:0000039", "Protein complexes can not be annotated to GO:0032991 (protein-containing complex) or its descendants", FailMode.HARD)
    
    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        # An implementation note: This is done by testing if the DB (column 1) is ComplexPortal. 
        # This will grab a subset of all actual Protein Complexes. This is noted in the rule description
        db = annotation[0]
        goterm = annotation[4]
        
        fails = (db == "ComplexPortal" and goterm == "GO:0032991")
        return self._result(not fails)

class GoRule42(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000042", "Qualifier: IKR evidence code requires a NOT qualifier", FailMode.HARD)

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        evidence = annotation[6]
        qualifier = self._list_terms(annotation[3])

        result = self._result(True)
        if evidence == "IKR":
            result = self._result("NOT" in qualifier)

        return result

class GoRule43(GoRule):
    
    def __init__(self):
        super().__init__("GORULE:0000043", "Check for valid combination of evidence code and GO_REF", FailMode.SOFT)
        self.ecomapping = ecomap.EcoMap()
        
    def _ref_curi_to_id(self, goref) -> str:
        """
        Changes reference IDs in the form of GO_REF:nnnnnnn to goref-nnnnnnn
        """
        return goref.lower().replace("_", "").replace(":", "-")
        
    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        if config.goref_metadata is None:
            return self._result(True)
        
        references = self._list_terms(annotation[5])
        evidence = annotation[6]
        
        for ref in references:
            allowed_eco = config.goref_metadata.get(self._ref_curi_to_id(ref), {}).get("evidence_codes", None)
            # allowed_eco will only not be none if the ref was GO_REF:nnnnnnn, that's the only time we care here
            if allowed_eco:
                allowed_evidence = [self.ecomapping.ecoclass_to_coderef(eco)[0] for eco in allowed_eco]
                if evidence not in allowed_evidence:
                    return self._result(False)
                    
        return self._result(True)


class GoRule46(GoRule):
    
    def __init__(self):
        super().__init__("GORULE:0000046", "The ‘with’ field (GAF column 8) must be the same as the gene product (GAF colummn 2) when annotating to ‘self-binding’ terms", FailMode.SOFT)
        self.self_binding_roots = ["GO:0042803", "GO:0051260", "GO:0051289", "GO:0070207", "GO:0043621", "GO:0032840"]
        self.self_binding_terms = None

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        if config.ontology is not None and self.self_binding_terms is None:
            all_terms = []
            # Initialize the self_binding terms if we have an ontology and we haven't already initialized the terms
            for binding_root in self.self_binding_roots:
                root_descendants = config.ontology.descendants(binding_root, relations=["subClassOf"], reflexive=True)
                all_terms += root_descendants
            
            self.self_binding_terms = set(all_terms)
        
        withfroms = self._list_terms(annotation[7])
        goterm = annotation[4]
        objectid = annotation[1]
        
        if goterm in self.self_binding_terms:
            # Then we're in the self-binding case, and check if object ID is in withfrom
            return self._result(objectid in withfroms)
            
        return self._result(True)

class GoRule50(GoRule):

    def __init__(self):
        super().__init__("GORULE:0000050", "Annotations to ISS, ISA and ISO should not be self-referential", FailMode.SOFT)
        self.the_evidences = ["ISS", "ISA", "ISO"]

    def test(self, annotation: List, config: assocparser.AssocParserConfig) -> TestResult:
        # should not have the same identifier in the 'gene product column' (column 2) and in the 'with/from' column (column 8)
        evidence = annotation[6]
        result = self._result(True)
        if evidence in self.the_evidences:
            # Ensure the gp ID is not an entry in withfrom
            result = self._result(annotation[1] not in self._list_terms(annotation[7]))

        return result


GoRules = enum.Enum("GoRules", {
    "GoRule02": GoRule02(),
    "GoRule06": GoRule06(),
    "GoRule07": GoRule07(),
    "GoRule08": GoRule08(),
    "GoRule11": GoRule11(),
    "GoRule13": GoRule13(),
    "GoRule15": GoRule15(),
    "GoRule16": GoRule16(),
    "GoRule17": GoRule17(),
    "GoRule18": GoRule18(),
    "GoRule26": GoRule26(),
    "GoRule28": GoRule28(),
    "GoRule29": GoRule29(),
    "GoRule30": GoRule30(),
    "GoRule37": GoRule37(),
    "GoRule39": GoRule39(),
    "GoRule42": GoRule42(),
    "GoRule43": GoRule43(),
    "GoRule46": GoRule46(),
    "GoRule50": GoRule50()
})

GoRulesResults = collections.namedtuple("GoRulesResults", ["all_results", "annotation"])
def test_go_rules(annotation: List, config: assocparser.AssocParserConfig) -> GoRulesResults:
    all_results = {}

    active_annotation = annotation
    for rule in list(GoRules):
        result = rule.value.run_test(active_annotation, config)
        # Accumulate all repairs performed  by all tests to the annotation
        active_annotation = result.result
        all_results[rule.value] = result

    return GoRulesResults(all_results, active_annotation)
