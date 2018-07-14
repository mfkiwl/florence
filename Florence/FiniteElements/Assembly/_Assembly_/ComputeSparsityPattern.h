#include <vector>
#include <algorithm>
#include <numeric>
#include <functional>
#include <cstdint>

inline void _ComputeSparsityPattern_  (
            const int *elements,
            const int *idx_start,
            const int *elem_container,
            int nvar,
            int nnode,
            int nelem,
            int nodeperelem,
            int idx_start_size,
            int *counts,
            int *indices,
            int &nnz
            )
{
    for (int i=1; i<idx_start_size; ++i) {
        std::vector<int> local_nodes((idx_start[i]-idx_start[i-1])*nodeperelem);
        int counter = 0;
        for (int j=idx_start[i-1]; j<idx_start[i]; ++j) {
            const int elem_container_j = nodeperelem*elem_container[j];
            for (int k=0; k<nodeperelem; ++k) {
                local_nodes[counter] = elements[elem_container_j+k];
                counter++;
            }
        }
        std::sort(local_nodes.begin(), local_nodes.end());
        auto last = std::unique(local_nodes.begin(), local_nodes.end());
        local_nodes.erase(last, local_nodes.end());
        counts[i-1] = local_nodes.size();

        for (int j=0; j<nvar; ++j) {
            for (int k=0; k<local_nodes.size(); ++k) {
                const int const_elem_retriever = local_nodes[k];
                for (int l=0; l<nvar; ++l) {
                    indices[nnz] = nvar*const_elem_retriever+l;
                    nnz++;
                }
            }
        }

    }
}




inline void _ComputeDataIndices_  (
            const int *indices,
            const int *indptr,
            int nelem,
            int nvar,
            int nodeperelem,
            const int *elements,
            const long *sorter,
            int *data_local_indices,
            int *data_global_indices
            ) {

    int ndof = nvar*nodeperelem;
    int local_capacity = ndof*ndof;
    int *current_row_column = (int*)malloc(sizeof(int)*ndof);
    int *current_row_column_local = (int*)malloc(sizeof(int)*ndof);

    for (int elem=0; elem<nelem; ++elem) {

        for (int counter=0; counter<nodeperelem; ++ counter) {
            const int const_elem_retriever = nvar*elements[elem*nodeperelem+counter];
            for (int ncounter=0; ncounter<nvar; ++ncounter) {
                current_row_column[nvar*counter+ncounter] = const_elem_retriever+ncounter;
            }
        }

        for (int counter=0; counter<nodeperelem; ++ counter) {
            const int node = sorter[elem*nodeperelem+counter];
            for (int ncounter=0; ncounter<nvar; ++ncounter) {
                current_row_column_local[nvar*counter+ncounter] = node*nvar+ncounter;
            }
        }


        for (int i=0; i<ndof; ++i) {
            const int nnz = indptr[current_row_column[i]+1] - indptr[current_row_column[i]];
            int *search_space = (int*)malloc(sizeof(int)*nnz);
            for (int k=0; k<nnz; ++k) {
                search_space[k] = indices[indptr[current_row_column[i]]+k];
            }

            for (int j=0; j<ndof; ++j) {
                int Iterr = std::find(search_space,search_space+nnz,current_row_column[j]) - search_space;
                data_global_indices[elem*local_capacity+i*ndof+j] = indptr[current_row_column[i]] + Iterr;
                data_local_indices[elem*local_capacity+i*ndof+j] = current_row_column_local[i]*ndof+current_row_column_local[j];
            }
            free(search_space);
        }
    }

    free(current_row_column);
    free(current_row_column_local);
}

