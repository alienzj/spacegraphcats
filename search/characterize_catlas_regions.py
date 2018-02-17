#! /usr/bin/env python
"""
Choose catlas subtrees between no larger than --maxsize and no smaller
than --minsize in number of k-mers, and extract summary information on
abundances of kmers within the subtrees.
"""
import argparse
import os
import sys
import collections
import math
import sourmash_lib
from sourmash_lib._minhash import hash_murmur
import time
import numpy
import pandas
import pickle

import screed
from . import search_utils
from .frontier_search import find_shadow


def make_all(ksize):
    DNA = 'ACGT'

    x = []
    def add(sofar, n):
        if n == 0:
            x.append("".join(sofar))
        else:
            for ch in DNA:
                add(sofar + ch, n-1)

    add("", ksize)
    return x

def main(args=sys.argv[1:]):
    p = argparse.ArgumentParser()
    p.add_argument('catlas_prefix', help='catlas prefix')
    p.add_argument('output')
    p.add_argument('--maxsize', type=float, default=100000)
    p.add_argument('--minsize', type=float, default=5000)
    p.add_argument('-k', '--ksize', default=5, type=int,
                   help='k-mer size for vectors')
    args = p.parse_args(args)

    print('minsize: {:g}'.format(args.minsize))
    print('maxsize: {:g}'.format(args.maxsize))
    print('ksize: {}'.format(args.ksize))

    basename = os.path.basename(args.catlas_prefix)
    catlas = os.path.join(args.catlas_prefix, 'catlas.csv')
    domfile = os.path.join(args.catlas_prefix, 'first_doms.txt')

    # load catlas DAG
    top_node_id, dag, dag_up, dag_levels, cdbg_to_catlas = search_utils.load_dag(catlas)
    print('loaded {} nodes from catlas {}'.format(len(dag), catlas))

    # load mapping between dom nodes and cDBG/graph nodes:
    layer1_to_cdbg = search_utils.load_layer1_to_cdbg(cdbg_to_catlas, domfile)
    print('loaded {} layer 1 catlas nodes'.format(len(layer1_to_cdbg)))

    # find the contigs filename
    contigs = os.path.join(args.catlas_prefix, 'contigs.fa.gz')

    # ...and catlas node sizes
    print('loading contig size info')
    cdbg_kmer_sizes, cdbg_weighted_kmer_sizes = search_utils.load_cdbg_size_info(args.catlas_prefix)
    node_kmer_sizes, node_weighted_kmer_sizes = search_utils.decorate_catlas_with_kmer_sizes(layer1_to_cdbg, dag, dag_levels, cdbg_kmer_sizes, cdbg_weighted_kmer_sizes)

    ### everything is loaded!

    # find highest nodes with kmer size less than given max_size
    def find_terminal_nodes(node_id, max_size):
        node_list = set()

        if not dag[node_id]:
            node_list.add(node_id)
            return node_list

        for sub_id in dag[node_id]:
            size = node_kmer_sizes[sub_id]

            if size < max_size:
                node_list.add(sub_id)
            else:
                children = find_terminal_nodes(sub_id, max_size)
                node_list.update(children)

        return node_list

    print('finding terminal nodes for {}.'.format(args.maxsize))
    nodes = find_terminal_nodes(top_node_id, args.maxsize)

    nodes = { n for n in nodes if node_kmer_sizes[n] > args.minsize }
    
    print('{} nodes between {} and {} in k-mer size'.format(len(nodes), args.minsize, args.maxsize))
    print('containing {} level1 nodes of {} total'.format(len(find_shadow(nodes, dag)), len(layer1_to_cdbg)))

    node_kmers = sum([ node_kmer_sizes[n] for n in nodes ])
    print('containing {} kmers of {} total ({:.1f}%)'.format(node_kmers, node_kmer_sizes[top_node_id], node_kmers / node_kmer_sizes[top_node_id] * 100))

    ### now build cdbg -> subtree/group ID

    cdbg_to_group = {}
    for n in nodes:
        shadow = find_shadow([n], dag)
        for level1_node in shadow:
            for cdbg_id in layer1_to_cdbg[level1_node]:
                assert cdbg_id not in cdbg_to_group
                cdbg_to_group[cdbg_id] = n

    # record group info - here we are using the MinHash class to track
    # k-mer abundances.
    group_info = {}
    group_ident = {}
    for n in nodes:
        group_info[n] = sourmash_lib.MinHash(n=0, ksize=args.ksize,
                                             scaled=1, track_abundance=1)
        group_ident[n] = sourmash_lib.MinHash(n=0, ksize=31, scaled=1000)

    # aaaaaand iterate over contigs, collecting abundances from all contigs
    # in a group.
    for record_n, record in enumerate(screed.open(contigs)):
        if record_n % 10000 == 0:
            print('...', record_n, end='\r')
        cdbg_id = int(record.name)
        group_id = cdbg_to_group.get(cdbg_id)
        
        if group_id is not None:
            # keep/measure!
            mh = group_info[group_id]
            mh.add_sequence(record.sequence, True)
            group_ident[group_id].add_sequence(record.sequence, True)

    # ok, now we have a pile of k-mer vectors of size 4**args.ksize;
    # output in numpy format.

    # first, make a consistently ordered list of all k-mers, and convert
    # them into hashes.
    all_kmers = make_all(args.ksize)
    all_kmer_hashes = list(set([ hash_murmur(i) for i in all_kmers ]))
    all_kmer_hashes.sort()

    # now, build a matrix of GROUP_N rows x 4**ksize columns, where each
    # row will be the set of k-mer abundances associated with each group.
    V = numpy.zeros((len(group_info), 4**args.ksize), dtype=numpy.uint16)
    node_id_to_group_idx = {}
    for i, n in enumerate(group_info):
        mh = group_info[n]
        vec = dict(mh.get_mins(with_abundance=True))
        vec = [ vec.get(hashval,0) for hashval in all_kmer_hashes ]
        vec = numpy.array(vec)
        V[i] = vec

        node_id_to_group_idx[n] = i

    # save!
    print('saving matrix of size {} to {}'.format(str(V.shape), args.output))
    with open(args.output, 'wb') as fp:
        numpy.save(fp, V)

    with open(args.output + '.node_ids', 'wb') as fp:
        pickle.dump(node_id_to_group_idx, fp)

    with open(args.output + '.node_mh', 'wb') as fp:
        pickle.dump(group_ident, fp)


if __name__ == '__main__':
    main()
