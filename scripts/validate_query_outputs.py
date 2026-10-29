"""Independent checks of true returned IDs, predicates, distances and Recall."""
from array import array
import mmap
from pathlib import Path
import statistics
import struct


def read_csr(path):
    with Path(path).open('rb') as f:
        rows, cols, nnz = struct.unpack('<3q', f.read(24))
        ptr, labels, values = array('q'), array('i'), array('f')
        ptr.fromfile(f, rows + 1)
        labels.fromfile(f, nnz)
        values.fromfile(f, nnz)
    return rows, ptr, labels, values


def labels_at(csr, row):
    _, ptr, labels, values = csr
    return {labels[i] for i in range(ptr[row], ptr[row + 1]) if values[i] != 0}


class DatasetValidator:
    def __init__(self, tier):
        self.tier = Path(tier)
        self.base_metadata = read_csr(self.tier / 'base.metadata.spmat')
        self.base_file = (self.tier / 'base.u8bin').open('rb')
        self.base = mmap.mmap(self.base_file.fileno(), 0, access=mmap.ACCESS_READ)
        self.n, self.dim = struct.unpack_from('<2I', self.base)
        self.node_labels = {}

    def close(self):
        self.base.close()
        self.base_file.close()

    def validate(self, bucket, prefix, budget):
        work = self.tier / 'workloads' / bucket
        query = (work / 'query.u8bin').read_bytes()
        nq, dim = struct.unpack_from('<2I', query)
        assert nq == 200 and dim == self.dim
        qmeta = read_csr(work / 'query.metadata.spmat')
        gt_raw = (work / 'ground_truth.ids.ibin').read_bytes()
        gt_n, gt_k = struct.unpack_from('<2I', gt_raw)
        assert gt_n == nq and gt_k >= 10
        ids_raw = Path(f'{prefix}.L{budget}.u32').read_bytes()
        ids = struct.unpack(f'<{nq*10}I', ids_raw)
        counts = struct.unpack(f'<{nq}I', Path(f'{prefix}.L{budget}.u32.counts').read_bytes())
        total_recall, valid_queries = 0.0, 0
        for q in range(nq):
            count = counts[q]
            assert 0 <= count <= 10
            result = ids[q*10:q*10+count]
            assert len(set(result)) == count, ('duplicate actual result', bucket, q)
            assert all(x == 0 for x in ids[q*10+count:q*10+10]), 'unexpected padding'
            predicate = labels_at(qmeta, q)
            qvec = query[8 + q*dim:8 + (q+1)*dim]
            distances = []
            for node in result:
                assert node < self.n
                if node not in self.node_labels:
                    self.node_labels[node] = labels_at(self.base_metadata, node)
                assert predicate.issubset(self.node_labels[node]), ('filter violation', bucket, q, node)
                vec = self.base[8 + node*dim:8 + (node+1)*dim]
                distances.append(sum((a-b)**2 for a,b in zip(qvec,vec)))
            assert distances == sorted(distances), ('distance order violation', bucket, q)
            gt = struct.unpack_from('<10I', gt_raw, 8 + q*gt_k*4)
            gt_set = {x for x in gt if x != 0xffffffff}
            if gt_set:
                total_recall += len(set(result) & gt_set) / len(gt_set)
                valid_queries += 1
        return {
            'predicate_checks_passed': True,
            'unique_ids_and_distance_order_passed': True,
            'recall_percent_recomputed': total_recall / valid_queries * 100,
            'actual_returned_ids': sum(counts),
            'padded_slots': nq*10-sum(counts),
            'mean_returned_per_query': statistics.mean(counts),
            'queries_with_full_top10': sum(n == 10 for n in counts),
            'queries_with_no_results': sum(n == 0 for n in counts),
            'min_returned': min(counts),
        }
