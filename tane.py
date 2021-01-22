'''
Implementation of the Functional Dependency Canonical Cover Miner TANE as described in:
[1] Hutala et al. - TANE: An Efficient Algorithm for Discovering Functional Approximate Dependencies. 1999.

Copyright (C) 2018 Victor Codocedo <firstname.lastname@gmail.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import sys
import time
from fca.defs.patterns.hypergraphs import TrimmedPartitionPattern
from fca.io.transformers import List2PartitionsTransformer
from itertools import combinations

# Get reduce for Python 3+
try:
    from functools import reduce
except ImportError:
    pass

##########################################################################################
## UTILS
##########################################################################################
def read_db(path):
    hashes = {}
    with open(path, 'r') as fin:
        for t, line in enumerate(fin):
            line = line.strip()
            if line == '':
                break
            for i, s in enumerate(line.split(',')):
                hashes.setdefault(i, {}).setdefault(s, set([])).add(t)# [(i, s)] = len(hashes)
        return [PPattern.fix_desc(list(hashes[k].values())) for k in sorted(hashes.keys())]

def tostr(atts):
    return ''.join([chr(65+i) for i in atts])

##########################################################################################
## CLASSES
##########################################################################################
class PPattern(TrimmedPartitionPattern):
    '''
    Represents the Stripped Partition
    '''
    @classmethod
    def intersection(cls, desc1, desc2):
        '''
        Procedure STRIPPED_PRODUCT defined in [1]
        '''
        new_desc = []
        T = {}
        S = {}
        for i, k in enumerate(desc1):
            for t in k:
                T[t] = i
            S[i] = set([])
        for i, k in enumerate(desc2):
            for t in k:
                if T.get(t, None) is not None:
                    S[T[t]].add(t)
            for t in k:
                if T.get(t, None) is not None:
                    if len(S[T[t]]) > 1:
                        new_desc.append(S[T[t]])
                    S[T[t]] = set([])
        return new_desc


class PartitionsManager(object):
    '''
    Manages the cache of already calcualted partitions.
    [1] is not very specific on how to manage partititions and memory.
    Our solution is this class where partitions are registered and cached
    TANE algorithm can access partitions using the cache.
    Partitions are calculated as an intersection or product (as mentioned in [1])
    of two partitions. This is done in GENERATE_NEXT_LEVEL when references to the
    two super-partitions are available.
    Cache is organized by levels reflecting the phases of TANE.
    Only 3 phases have to be available at all time, the current, the previous and the next.
    As such, purge_old_level purges the cache of unused levels.
    Purge cache is called at the end of each TANE phase.
    '''
    def __init__(self, T):
        '''
        Initializes the cache
        '''
        self.T = T
        self.cache = {0:None, 1:{(i,):j for i, j in enumerate(T)}}
        self.current_level = 1
    
    def new_level(self):
        '''
        Creates a cache for the new level
        '''
        self.current_level += 1
        self.cache[self.current_level] = {}
    
    def purge_old_level(self):
        '''
        Memory wipe of unused cache
        '''
        del self.cache[self.current_level-2]

    def register_partition(self, X, X0, X1):
        '''
        Registers partition of attributes in X, using partitions 
        already calculated of attributes in X0 and X1
        '''
        self.cache[len(X)][X] = PPattern.intersection(self.cache[len(X0)][X0], self.cache[len(X1)][X1])

    def check_fd(self, X, y):
        '''
        Main difference with [1], we do not check using procedure "e" 
        to check and FD, but we use partition subsumption
        Seems more efficient
        '''
        if not bool(X):
            return False
        left = self.cache[len(X)][X]
        return PPattern.leq(left, self.T[y])

    def is_superkey(self, X):
        return not bool(self.cache[len(X)][X])

class rdict(dict):
    '''
    Recursive dictionary implementing Cplus
    '''
    def __init__(self, *args, **kwargs):
        super(rdict, self).__init__(*args, **kwargs)
        self.itemlist = super(rdict, self).keys()
    def __getitem__(self, key):
        if key not in self:
            self[key] = self.recursive_search(key)
        return super(rdict, self).__getitem__(key)

    def recursive_search(self, key):
        return reduce(set.intersection, [self[tuple(key[:i]+key[i+1:])] for i in range(len(key))])

##########################################################################################
## PROCEDURES
##########################################################################################
def calculate_e(X, XA, R, checker):
    '''
    Procedure e defined in [1]
    Not in use now
    '''
    e = 0
    T = {}
    if not bool(X):
        return -1
    X = checker.cache[len(X)][X]
    XA = checker.cache[len(XA)][XA]
    
    for c in XA:
        T[next(iter(c))] = len(c)
    for c in X:
        m = 1
        for t in c:
            m = max(m, T.get(t, 0))
        e += len(c) - m
    return float(e)/len(R)

def prefix_blocks(L):
    '''
    Procedure PREFIX_BLOCKS described in [1]
    '''
    blocks = {}
    for atts in L:
        blocks.setdefault(atts[:-1],[]).append(atts)
    return blocks.values()

##########################################################################################
## TANE ALGORITHM
##########################################################################################

class TANE(object):
    '''
    As seen on TV [1]
    '''
    def __init__(self, T):
        self.T = T
        self.rules = []

        self.pmgr = PartitionsManager(T)
        self.R = range(len(T))
        

        self.Cplus = rdict()
        self.Cplus[tuple([])] = set(self.R)


    def compute_dependencies(self, L):
        '''
        Procedure COMPUTE_DEPENDENCIES described in [1]
        '''
        for X in L:
            for y in self.Cplus[X].intersection(X):
                a = X.index(y)
                LHS = X[:a]+X[a+1:]
                if self.pmgr.check_fd(LHS, y):
                    self.rules.append((LHS, y))
                    self.Cplus[X].remove(y)
                    map(self.Cplus[X].remove, filter(lambda i: i not in X, self.Cplus[X]))

    def prune(self, L):
        '''
        Procedure PRUNE described in [1]
        '''
        clean_idx = set([])
        for X in L:
            if not bool(self.Cplus[X]):
                clean_idx.add(X)
            if self.pmgr.is_superkey(X): # Is Superkey, since it's a stripped partition, then it's an empty set
                for y in filter(lambda x: x not in X, self.Cplus[X]):
                    if y in reduce(set.intersection, [self.Cplus[tuple(sorted(X[:b]+X[b+1:]+(y,)))] for b in range(len(X))]):
                        self.rules.append((X, y))
                clean_idx.add(X)
        for X in clean_idx:
            L.remove(X)

    def prefix_blocks(self, L):
        '''
        Procedure PREFIX_BLOCKS described in [1]
        '''
        blocks = {}
        for atts in L:
            blocks.setdefault(atts[:-1],[]).append(atts)
        return blocks.values()

    def generate_next_level(self, L):
        '''
        Procedure GENERATE_NEXT_LEVEL described in [1]
        '''
        self.pmgr.new_level()
        next_L = set([])
        for k in prefix_blocks(L):
            for i, j in combinations(k, 2):
                if i[-1] < j[-1]:
                    X = i + (j[-1],)
                else:
                    X = j + (i[-1],)
                if all(X[:a]+X[a+1:] in L for a, x in enumerate(X)):
                    next_L.add(X)
                    # WE ADD THIS LINE, SEEMS A BETTER ALTERNATIVE TO CALCULATE THE PARTITION HERE WHEN
                    # WE HAVE REFERENCES TO BOTH PARTITIONS USED TO CALCULATE IT
                    self.pmgr.register_partition(X, i, j) 
        return next_L

    def memory_wipe(self):
        '''
        FREE SOME MEMORY!!!
        '''
        self.pmgr.purge_old_level()

    def run(self):
        '''
        Procedure TANE in [1]
        '''
        L1 = set([tuple([i]) for i in self.R])
        L = [None, L1]
        l = 1 
        while bool(L[l]):
            self.compute_dependencies(L[l])
            self.prune(L[l])
            L.append(self.generate_next_level(L[l]))
            l = l+1
            # MEMORY WIPE
            L[l-1] = None 
            self.memory_wipe()

if __name__ == "__main__":
    T = read_db(sys.argv[1])
    tane = TANE(T)
    t0 = time.time()
    tane.run()
    print ("\t=> Execution Time: {} seconds".format(time.time()-t0))
    print ('\t=> {} Rules Found'.format(len(tane.rules)))
    
