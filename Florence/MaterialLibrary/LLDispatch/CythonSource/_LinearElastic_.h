#include "_MaterialBase_.h"

template<typename U>
class _LinearElastic_ : public _MaterialBase_<U> {
public:
    U mu;
    U lamb;

    FASTOR_INLINE _LinearElastic_() = default;

    FASTOR_INLINE
    _LinearElastic_(U mu, U lamb) {
        this->mu = mu;
        this->lamb = lamb;
    }

    FASTOR_INLINE
    void SetParameters(U mu, U lamb){
        this->mu = mu;
        this->lamb = lamb;
    }


    template<typename T=U, size_t ndim>
    FASTOR_INLINE
    std::tuple<Tensor<T,ndim,ndim>, typename MechanicsHessianType<T,ndim>::return_type>
    _KineticMeasures_(const T *Fnp) {

        // CREATE FASTOR TENSORS
        Tensor<T,ndim,ndim> F;
        // COPY NUMPY ARRAY TO FASTOR TENSOR
        copy_numpy(F,Fnp);

        Tensor<Real,ndim,ndim> I; I.eye2();
        Tensor<T,ndim,ndim> GradU = F - I;
        Tensor<T,ndim,ndim> strain = 0.5*(GradU + transpose(GradU));

        // COMPUTE CAUCHY STRESS TENSOR
        T tre = trace(strain);
        if (ndim == 2) {
            tre += 1.;
        }

        Tensor<T,ndim,ndim> stress = 2*mu*strain + lamb*tre*I;

        // FIND ELASTICITY TENSOR
        auto II_ijkl = einsum<Index<i,j>,Index<k,l>>(I,I);
        auto II_ikjl = permutation<Index<i,k,j,l>>(II_ijkl);
        auto II_iljk = permutation<Index<i,l,j,k>>(II_ijkl);

        Tensor<T,ndim,ndim,ndim,ndim> elasticity = mu * (II_ikjl + II_iljk) + lamb*II_ijkl;

        auto hessian = voigt(elasticity);

        auto kinetics = std::make_tuple(stress,hessian);
        return kinetics;
    }



    template<typename T>
    void KineticMeasures(T *Snp, T* Hnp, int ndim, int ngauss, const T *Fnp);

};

template<> template<>
void _LinearElastic_<Real>::KineticMeasures<Real>(Real *Snp, Real* Hnp,
    int ndim, int ngauss, const Real *Fnp) {

    if (ndim==3) {
        Tensor<Real,3,3> stress;
        Tensor<Real,6,6> hessian;
        for (int g=0; g<ngauss; ++g) {
            std::tie(stress,hessian) =_KineticMeasures_<Real,3>(Fnp+9*g);
            copy_fastor(Snp,stress,g*9);
            copy_fastor(Hnp,hessian,g*36);
        }
    }
    else if (ndim==2) {
        Tensor<Real,2,2> stress;
        Tensor<Real,3,3> hessian;
        for (int g=0; g<ngauss; ++g) {
            std::tie(stress,hessian) =_KineticMeasures_<Real,2>(Fnp+4*g);
            copy_fastor(Snp,stress,g*4);
            copy_fastor(Hnp,hessian,g*9);
        }
    }
}
