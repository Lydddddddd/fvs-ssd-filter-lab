#pragma once

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace pipeann {

// Exact query-local membership for dense node IDs [0, node_count).
// The bitmap owns its storage, so concurrent queries do not share marks.
// Construction zeroes ceil(node_count / 64) words; this cost is included in
// the query driver's wall-clock measurement.
class DenseVisited {
 public:
  explicit DenseVisited(std::size_t node_count)
      : node_count_(node_count), words_(node_count / 64 + (node_count % 64 != 0), 0) {}

  // Return true exactly once per valid node ID, matching set::insert.second.
  bool insert(std::uint32_t id) {
    if (id >= node_count_) {
      throw std::out_of_range("DenseVisited: node ID outside index");
    }
    auto &word = words_[id >> 6];
    const std::uint64_t mask = std::uint64_t{1} << (id & 63);
    const bool fresh = (word & mask) == 0;
    word |= mask;
    return fresh;
  }

  std::size_t storage_bytes() const { return words_.size() * sizeof(std::uint64_t); }

 private:
  std::size_t node_count_;
  std::vector<std::uint64_t> words_;
};

}  // namespace pipeann
