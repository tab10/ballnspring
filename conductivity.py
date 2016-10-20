"""


@author: Alex Kerr
"""

import itertools
from copy import deepcopy

import numpy as np
import scipy.linalg as linalg

def calculate_thermal_conductivity(mol, driverList, baseSize, gamma):
    
    #give each driver the same drag constant (Calculation gamma)
    
    #standardize the driverList
    driverList = np.array(driverList)
    
    stapled_index = 30
#    stapled_index=None
    
    from .operation import _calculate_hessian
    kMatrix = _calculate_hessian(mol, stapled_index, numgrad=False)
    
    gMatrix = _calculate_gamma_mat(len(mol), gamma, driverList)
    
    mMatrix = _calculate_mass_mat(mol.zList)
    
    val, vec = _calculate_thermal_evec(kMatrix, gMatrix, mMatrix)
    
    coeff = _calculate_coeff(val, vec, mMatrix, gMatrix)
    
    
    #find interactions that cross an interface        
    crossings = []
    atoms0 = mol.faces[0].attached
    atoms1 = mol.faces[1].attached
    
    if mol.ff.dihs:
        interactions = mol.dihList
    elif mol.ff.angles:
        interactions = mol.angleList
    elif mol.ff.lengths:
        interactions = mol.bondList

    for it in interactions:
        for atom in atoms0:
            if atom in it:
                #find elements that are part of the base molecule
                #if there are any, then add them to interactions
                elements = [x for x in it if x < baseSize]
                for element in elements:
                    crossings.append([atom, element])
        for atom in atoms1:
            if atom in it:
                elements = [x for x in it if x < baseSize]
                for element in elements:
                    crossings.append([element, atom])
                    
    #add nonbonded interactions
    ''' to 
        be 
        completed '''
                    
    #remove duplicate interactions
    crossings.sort()
    crossings = list(k for k,_ in itertools.groupby(crossings))
    print(crossings)
         
    #initialize the thermal conductivity value
    kappa = 0.
    
#    mullenTable = []
    mullenTable = None
                
    for crossing in crossings:
        i,j = crossing
        kappa += _calculate_power(i,j,val, vec, coeff, kMatrix, driverList, mullenTable)
#        kappa += _calculate_power_loop(i,j,val, vec, coeff, kMatrix, driverList, mullenTable)
    
    inspect(mol, val, vec, kMatrix, crossings, mullenTable)

#    import pprint
#    pprint.pprint(mullenTable)
    print(kappa)
    return kappa
#    return kappa, mullenTable
    
def _calculate_power_loop(i,j, val, vec, coeff, kMatrix, driverList, mullenTable):
    
    driver1 = driverList[1]    
    
    n = len(val)//2
    
    kappa = 0.
    
    for idim in [0,1,2]:
        for jdim in [0,1,2]:
            for driver in driver1:
                term = 0.
                for sigma in range(2*n):
                    cosigma = coeff[sigma, 3*driver + 1] + coeff[sigma, 3*driver +2] + coeff[sigma, 3*driver]
                    for tau in range(2*n):
                        cotau = coeff[tau, 3*driver] + coeff[tau, 3*driver+1] + coeff[tau, 3*driver+2]
                        try:
                            test= kMatrix[3*i + idim, 3*j + jdim]*(cosigma*cotau*(vec[:n,:][3*i + idim ,sigma])*(
                                    vec[:n,:][3*j + jdim,tau])*((val[sigma]-val[tau])/(val[sigma]+val[tau])))
                            if mullenTable is not None:
                                mullenTable.append(test)
                            term += test
                        except FloatingPointError:
                            print("Divergent term")
#                term *= kMatrix[3*i + idim, 3*j + jdim]
                kappa += term
            
    return kappa
    
def _calculate_power(i,j, val, vec, coeff, kMatrix, driverList, mullenTable):
    
    #assuming same drag constant as other driven atom
    driver1 = driverList[1]
    
    n = len(val)
    
    kappa = 0.
    
    val_sigma = np.tile(val, (n,1))
    val_tau = np.transpose(val_sigma)
    
    with np.errstate(divide="ignore", invalid="ignore"):
        valterm = np.true_divide(val_sigma-val_tau,val_sigma+val_tau)
    valterm[~np.isfinite(valterm)] = 0.
    
    for idim in [0,1,2]:
        for jdim in [0,1,2]:
            
            term3 = np.tile(vec[3*i + idim,:], (n,1))
            term4 = np.transpose(np.tile(vec[3*j + jdim,:], (n,1)))
            
            for driver in driver1:
    
                term1 = np.tile(coeff[:, 3*driver] + coeff[:, 3*driver+1] + coeff[:, 3*driver+2], (n,1))
                term2 = np.transpose(term1)
                
                termArr = kMatrix[3*i + idim, 3*j + jdim]*term1*term2*term3*term4*valterm
                if mullenTable is not None:
#                    mullenTable.append(kMatrix[3*i + idim, 3*j +jdim])
                #####
#                    mullenTable.append(termArr)
                ########
                    large_vals = np.where(np.absolute(termArr) > 250.)
##                    print(large_vals)
                    for x,y in zip(large_vals[0], large_vals[1]):
                        mullenTable.append([termArr[x, y], x, y, i, j])
#                        mullenTable.append([term1[x,y], term2[x,y], term3[x,y], term4[x,y], val_sigma[x,y], val_tau[x,y], valterm[x,y]])
#                        mullenTable.append(x)
#                term = kMatrix[3*i + idim, 3*j + jdim]*np.sum(term1*term2*term3*term4*valterm)
#                kappa += term
                kappa += np.sum(termArr)
                
    return kappa
    
def _calculate_coeff(val, vec, massMat, gMat):
    """Return the 2N x N Green's function coefficient matrix."""
    
    N = len(vec)//2
    
    #need to determine coefficients in eigenfunction/vector expansion
    # need linear solver to solve equations from notes
    # AX = B where X is the matrix of expansion coefficients
    
    A = np.zeros((2*N, 2*N), dtype=complex)
    A[:N,:] = vec[:N,:]

    #adding mass and damping terms to A
    lamda = np.tile(val, (N,1))

    A[N:,:] = np.multiply(A[:N,:], np.dot(massMat,lamda) + np.dot(gMat,np.ones((N,2*N))))
    
    #now prep B
    B = np.concatenate((np.zeros((N,N)), np.identity(N)), axis=0)

    return np.linalg.solve(A,B)
    
def _calculate_thermal_evec(K,G,M):
    
    N = len(M)
    
    a = np.zeros([N,N])
    a = np.concatenate((a,np.identity(N)),axis=1)
    b = np.concatenate((K,G),axis=1)
    c = np.concatenate((a,b),axis=0)
    
    x = np.identity(N)
    x = np.concatenate((x,np.zeros([N,N])),axis=1)
    y = np.concatenate((np.zeros([N,N]),-M),axis=1)
    z = np.concatenate((x,y),axis=0)
    
    w,vr = linalg.eig(c,b=z,right=True)
    
    return w,vr
    
def _calculate_mass_mat(zList):
    
    massList = []
    
    for z in zList:
        massList.append(amuDict[z])
        
    diagonal = np.repeat(np.array(massList), 3)
    
    return np.diag(diagonal)
    
def _calculate_gamma_mat(N,gamma, driverList):
    
    gmat = np.zeros((3*N, 3*N))
    driveList = np.hstack(driverList)
    
    for drive_atom in driveList:
        gmat[3*drive_atom  , 3*drive_atom  ] = gamma
        gmat[3*drive_atom+1, 3*drive_atom+1] = gamma
        gmat[3*drive_atom+2, 3*drive_atom+2] = gamma
        
    return gmat
    
def _calculate_ballandspring_k_mat(N,k0,nLists):
    """Return the Hessian of a linear chain of atoms assuming only nearest neighbor interactions."""
    
    KMatrix = np.zeros([3*N,3*N])
    
    for i,nList in enumerate(nLists):
        KMatrix[3*i  ,3*i  ] = k0*len(nList)
        KMatrix[3*i+1,3*i+1] = k0*len(nList)
        KMatrix[3*i+2,3*i+2] = k0*len(nList)
        for neighbor in nList:
            KMatrix[3*i  ,3*neighbor] = -k0
            KMatrix[3*i+1,3*neighbor+1] = -k0
            KMatrix[3*i+2,3*neighbor+2] = -k0
    
    return KMatrix