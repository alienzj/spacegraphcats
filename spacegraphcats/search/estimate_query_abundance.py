#! /usr/bin/env python
"""
Use the cDBG and the info.csv file to estimate the abundance of a query
genome.

The query genome should be largely or completely enclosed in the 
"""
import argparse
import os
import sys
import gzip
import khmer
import collections
import bbhash
import numpy
from collections import defaultdict

import screed

from spacegraphcats.utils.logging import log
from . import search_utils


def main():
    p = argparse.ArgumentParser()
    p.add_argument('catlas_prefix', help='catlas prefix')
    p.add_argument('query')
    p.add_argument('-k', '--ksize', default=31, type=int,
                   help='k-mer size (default: 31)')
    p.add_argument('-o', '--output', type=argparse.FileType('wt'))
    p.add_argument('-v', '--verbose', action='store_true')
    args = p.parse_args()

    contigs = os.path.join(args.catlas_prefix, 'contigs.fa.gz')
    x = search_utils.load_cdbg_size_info(args.catlas_prefix)
    cdbg_kmer_sizes, cdbg_weighted_kmer_sizes = x

    # load k-mer MPHF index
    kmer_idx = search_utils.load_kmer_index(args.catlas_prefix)

    # build hashes for all the query k-mers
    print('loading query kmers...')
    bf = khmer.Nodetable(args.ksize, 1, 1)

    x = set()
    n = 0

    query_kmers = set()
    for record in screed.open(args.query):
        query_kmers.update(bf.get_kmer_hashes(record.sequence))

    # find the list of cDBG nodes that contain at least one query k-mer
    cdbg_match_counts = kmer_idx.get_match_counts(query_kmers)

    # calculate number of nodes found -
    cdbg_shadow = set(cdbg_match_counts.keys())

    # calculate the sum total k-mers across all of the matching nodes
    cdbg_node_sizes = {}
    cdbg_total_weighted = 0.
    for cdbg_id in cdbg_shadow:
        cdbg_node_sizes[cdbg_id] = kmer_idx.get_cdbg_size(cdbg_id)
        cdbg_total_weighted += cdbg_weighted_kmer_sizes[cdbg_id]

    # output some stats
    total_found = sum(cdbg_match_counts.values())
    f_found = total_found / len(query_kmers)
    print('...done loading & counting query k-mers in cDBG.')
    print('containment: {:.1f}%'.format(f_found * 100))

    total_kmers_in_cdbg_nodes = sum(cdbg_node_sizes.values())
    sim = total_found / total_kmers_in_cdbg_nodes
    print('similarity: {:.1f}%'.format(sim * 100))

    print('weight:', cdbg_total_weighted, cdbg_total_weighted / len(query_kmers))

    if not args.output:
        sys.exit(0)

    sys.exit(0)


if __name__ == '__main__':
    main()
