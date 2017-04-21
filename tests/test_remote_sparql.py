from ontobio.ontol_factory import OntologyFactory
import logging

HAS_PART = 'BFO:0000051'
PART_OF = 'BFO:0000050'

QUALITY = 'PATO:0000001'
PLOIDY = 'PATO:0001374'
EUPLOID = 'PATO:0001393'
SHAPE = 'PATO:0000052'
Y_SHAPED = 'PATO:0001201'
PENTAPLOID = 'PATO:0001383'
SWOLLEN = 'PATO:0001851'
DILATED = 'PATO:0001571'
INCREASED_SIZE = 'PATO:0000586'
PROTRUDING = 'PATO:0001598'
MORPHOLOGY = 'PATO:0000051'
ABSENT = 'PATO:0000462'

def test_remote_sparql():
    """
    Load ontology from remote SPARQL endpoint
    """
    factory = OntologyFactory()
    print("Creating ont")
    ont = factory.create('pato')

    ploidy = ont.node(PLOIDY)
    print("PLOIDY: {}".format(ploidy))
    assert ont.label(PLOIDY) == 'ploidy'

    # exact match
    search_results = ont.search('shape')
    print("SEARCH (exact): {}".format(search_results))
    assert [SHAPE] == search_results

    # implicit regexp
    search_results = ont.search('%shape%')
    print("SEARCH (re, implicit): {}".format(search_results))
    assert SHAPE in search_results
    assert len(search_results)>10

    # explicit regexp
    search_results = ont.search('.*shape.*', is_regex=True)
    print("SEARCH (re, explicit): {}".format(search_results))
    assert SHAPE in search_results
    assert len(search_results)>10
    
    num_nodes = 0
    for n in ont.nodes():
        num_nodes = num_nodes+1
    assert num_nodes > 100

    ancs = ont.ancestors(PLOIDY)
    print("ANCS ploidy (all): {}".format(ancs))
    assert QUALITY in ancs
    assert PENTAPLOID not in ancs

    ancs = ont.ancestors(PLOIDY, relations=['subClassOf'])
    print("ANCS ploidy (subClassOf): {}".format(ancs))
    assert QUALITY in ancs
    assert PENTAPLOID not in ancs

    # this is a non-use case
    ancs = ont.ancestors(SWOLLEN, relations=[HAS_PART])
    print("ANCS swollen (has_part): {}".format(ancs))
    assert INCREASED_SIZE in ancs
    assert PROTRUDING in ancs
    assert len(ancs) == 2

    ancs = ont.ancestors(SWOLLEN, relations=['subClassOf'])
    print("ANCS swollen (has_part): {}".format(ancs))
    assert MORPHOLOGY in ancs
    assert QUALITY in ancs
    assert PROTRUDING not in ancs
    
    decs = ont.descendants(PLOIDY)
    print("DECS ploidy (all): {}".format(decs))
    assert QUALITY not in decs
    assert EUPLOID in decs
    assert PENTAPLOID in decs

    # this is a non-use case
    ancs = ont.descendants(INCREASED_SIZE, relations=[HAS_PART])
    print("ANCS increased size (has part): {}".format(ancs))
    assert SWOLLEN in ancs
    assert len(ancs) == 1

    subsets = ont.subsets()
    print("SUBSETS: {}".format(subsets))

    slim = ont.extract_subset('absent_slim')
    print("SLIM: {}".format(slim))
    assert ABSENT in slim
    assert QUALITY not in slim
