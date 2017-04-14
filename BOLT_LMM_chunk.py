import scipy as sp 
from scipy import stats
import numpy as np
import multiprocessing as mp
import h5py
import random
import math
import sys
import time

start_time = time.time()
print("Importing the phenotypes and the chromosome numbers...")

with h5py.File("Normalized_data.h5","r") as hf:
	data = hf.get('Y')
	Y= sp.array(data, dtype= "single")

with h5py.File("New_try.h5","r") as hf:
	data = hf["Chromosomes"]
	Chromosomes = sp.array(data, dtype= "single")

print("Execution time (importing):", round(time.time()-start_time,2),"seconds")
print("Shape of the array phenotypes:", Y.shape)
print("Shape of the array Chromosomes:", Chromosomes.shape)

N= Y.shape[0]
M= Chromosomes.shape[0]

## Step 1a : Estimate variance parameters

##---------------------------------------------------------
## Conjugate gradient iteration (in chunks)
##---------------------------------------------------------
## Name: conjugateGradientSolveChunks
## Purpose: Solving an equation of the form
##              Ax=b
## 			(where A is of the form XX'/M + d*I)
##          by the aid of conjugate gradient iteration.
##			Due to the composition of A, we have that
## 			Ax= (XX'/M + d*I)x= (1/M)*XX'x + d*x.
##			This expression can be calculated 
##        	much more efficient as the calculation
## 			needs less CPU time and memory.
## Input: 
## hf = a string specifying the hdf5-file that 
## 		includes the normalized genotype matrix X
## 		(NxM-matrix)
## b = N-vector
## x0 = N-vector, the initial value of x
## c1,c2 = real scalars
## chunk_size = the size of the chunks that should be 
## 				used (default = 1000)
## Output:
## x
##---------------------------------------------------------

def conjugateGradientSolveChunks(hf,x0,b,c1=1,c2=1, chunk_size=1000):

	(N,M)= h5py.File(hf, "r")['X'].shape
	x = x0
	XTx = sp.zeros(M, dtype="single")
	XXTx = sp.empty(N, dtype = "single")

	for chunk in range(0,N,chunk_size):
		X_chunk = h5py.File(hf, "r")['X'][chunk:chunk+chunk_size]
		XTx += sp.dot(X_chunk.T,x[chunk:chunk+chunk_size])

	for chunk in range(0,N,chunk_size):
		X_chunk = h5py.File(hf, "r")['X'][chunk:chunk+chunk_size]
		XXTx[chunk:chunk+X_chunk.shape[0]] = sp.dot(X_chunk,XTx)

	r = b-(sp.array(XXTx, dtype= "single")*float(c1)/float(M) + float(c2)*x)
	p=r
	rsold = sp.dot(r,r)
	norm = sp.sqrt(rsold)
	while norm>0.0005:

		XTx = sp.zeros(M, dtype="single")
		XXTx = sp.empty(N, dtype = "single")
		for chunk in range(0,N,chunk_size):
			X_chunk = h5py.File(hf, "r")['X'][chunk:chunk+chunk_size]
			XTx += sp.dot(X_chunk.T,p[chunk:chunk+chunk_size])

		for chunk in range(0,N,chunk_size):
			X_chunk = h5py.File(hf, "r")['X'][chunk:chunk+chunk_size]
			XXTx[chunk:chunk+X_chunk.shape[0]] = sp.dot(X_chunk,XTx)

		Ap = sp.array(XXTx, dtype= "single")*float(c1)/float(M) + float(c2)*p
		## alpha = step size
    	## alpha = t(r_{k-1})*r_{k-1}/(t(p_k)*A*p_k)
		alpha = rsold/(sp.dot(p,Ap))
		## x_k = x_{k-1} + alpha*p_k
		x = x+alpha*p
		## r_k = r_{k-1}-alpha*A*p_k
		r = r-alpha*Ap
		rsnew = sp.dot(r,r)
		## beta = t(r_{k-1})*r_{k-1}/(t(r_{k-2})*r_{k-2})
		## p = search direction
		## p_k = r_{k-1} + beta*p_{k-1}
		p = r+(rsnew/rsold)*p
		norm = sp.sqrt(rsnew)
		rsold = rsnew
	return(x)


##---------------------------------------------------------
## Compute f_{REML}(log(delta)) 
##---------------------------------------------------------
## Name: evalfREML
## Purpose: Compute f_{REML}(log(delta)), where
##          f_{REML}(log(delta)) = log((sum(beta.hat_data^2)/
##          sum(e.hat_data^2))/(E[sum(hat.beta^2)]/E[sum(
##              e.hat_data^2)]))
## Input: 
## logDelta = log(delta) = log(sigma.e^2/sigma.g^2) 
## MCtrials = Number of Monte Carlo simulations
## hf = a string specifying the hdf5-file that 
## 		includes the normalized genotype matrix X
## 		(NxM-matrix)
## Y = phenotype vector, N-vector
## beta_rand = random SNP effects
## e_rand_unscaled = random environmental effects
## chunk_size = the size of the chunks that should be 
## 				used (default = 1000)
## Output:
## The evaluated function, f_{REML}
##---------------------------------------------------------

def evalfREML(logDelta,MCtrials,hf,Y,beta_rand,e_rand_unscaled, chunk_size=1000):

	(N,M)= h5py.File(hf, "r")['X'].shape
	delta = sp.exp(logDelta, dtype= "single")
	y_rand = sp.empty((N,MCtrials), dtype= "single")
	H_inv_y_rand = sp.empty((N,MCtrials), dtype= "single")
	beta_hat_rand = sp.zeros((M,MCtrials), dtype= "single")
	e_hat_rand = sp.empty((N,MCtrials), dtype= "single")

	## Defining the initial vector x0
	x0 = sp.zeros(N, dtype= "single")
	for t in range(0,MCtrials):

		Xbeta = sp.empty(N, dtype = "single")
		## build random phenotypes using pre-generated components
		for chunk in range(0,N,chunk_size):
			X_chunk = h5py.File(hf, "r")['X'][chunk:chunk+chunk_size]
			Xbeta[chunk:chunk+X_chunk.shape[0]]= sp.dot(X_chunk, beta_rand[:,t])

		y_rand[:,t] = Xbeta+sp.sqrt(delta)*e_rand_unscaled[:,t]
		## compute H^(-1)%*%y.rand[,t] by the aid of conjugate gradient iteration
		H_inv_y_rand[:,t] = conjugateGradientSolveChunks(hf=hf,x0=x0,b=y_rand[:,t],c2=delta, chunk_size=chunk_size)
		## compute BLUP estimated SNP effect sizes and residuals
		for chunk in range(0,N,chunk_size):
			X_chunk = h5py.File(hf, "r")['X'][chunk:chunk+chunk_size]
			beta_hat_rand[:,t] += sp.dot(X_chunk.T,H_inv_y_rand[chunk:chunk+chunk_size,t])

		e_hat_rand[:,t] = H_inv_y_rand[:,t]
		#print("In evalfREML: Iteration %d has been completed..." % t)

	## compute BLUP estimated SNP effect sizes and residuals for real phenotypes
	e_hat_data = conjugateGradientSolveChunks(hf=hf,x0=x0,b=Y,c2=delta, chunk_size=chunk_size)
	beta_hat_data = sp.zeros(M,dtype="single")
	for chunk in range(0,N,chunk_size):
			X_chunk = h5py.File(hf, "r")['X'][chunk:chunk+chunk_size]
			beta_hat_data += sp.dot(X_chunk.T,e_hat_data[chunk:chunk+chunk_size])
	
	## evaluate f_REML
	f = sp.log((sp.sum(beta_hat_data**2)/sp.sum(e_hat_data**2))/(sp.sum(beta_hat_rand**2)/sp.sum(e_hat_rand**2)))
	return(f)


print("Step 1a : Estimate variance parameters...")
step = time.time()

## Set the number of Monte Carlo trials
MCtrials = max(min(4e9/(N**2),15),3)
print("The number of MC trials is:", MCtrials)

## generate random SNP effects
beta_rand = stats.norm.rvs(0,1,size=(M,MCtrials))*sp.sqrt(1.0/float(M))
beta_rand.astype(dtype="single")
## generate random environmental effects
e_rand_unscaled = stats.norm.rvs(0,1,size=(N,MCtrials))
e_rand_unscaled.astype(dtype="single")

h12 = 0.25
logDelta = [sp.log((1-h12)/h12)]

## Perform first fREML evaluation
print("Performing the first fREML evaluation...")
start_time = time.time()

f = [evalfREML(logDelta=logDelta[0],MCtrials=MCtrials,hf="Normalized_data.h5",Y=Y,beta_rand=beta_rand,e_rand_unscaled=e_rand_unscaled)]
print("Execution time (first fREML):", round(time.time()-start_time,2),"seconds")

if f[0]<0:
	h22=0.125
else:
	h22=0.5

logDelta.append(sp.log((1-h22)/h22))

## Perform second fREML evaluation
print("Performing the second fREML evaluation...")
start_time = time.time()

f.append(evalfREML(logDelta=logDelta[1],MCtrials=MCtrials,hf="Normalized_data.h5",Y=Y,beta_rand=beta_rand,e_rand_unscaled=e_rand_unscaled))
print("Execution time (second fREML):", round(time.time()-start_time,2),"seconds")

## Perform up to 5 steps of secant iteration
print("Performing up to 5 steps of secant iteration...")
for s in range(2,7):
	logDelta.append((logDelta[s-2]*f[s-1]-logDelta[s-1]*f[s-2])/(f[s-1]-f[s-2]))
	## check convergence
	if abs(logDelta[s]-logDelta[s-1])<0.01:
		break
	f.append(evalfREML(logDelta=logDelta[s],MCtrials=MCtrials,hf="Normalized_data.h5",Y=Y,beta_rand=beta_rand,e_rand_unscaled=e_rand_unscaled))
	print("Iteration %d has been completed successfully." % (s-1))

delta = sp.exp(logDelta[-1])
print("The final delta:",delta) # 0.17609251449105767

x0 = sp.zeros(N, dtype= "single")
H_inv_y_data = conjugateGradientSolveChunks(hf="Normalized_data.h5",x0=x0,b=Y,c2=delta)

sigma_g = sp.dot(Y,H_inv_y_data)/float(N)
sigma_e = delta*sigma_g
print("sigma.g=",sigma_g) # 0.80200006131763968
print("sigma.e=",sigma_e) # 0.14122620741940561

print("Step 1a took", round((time.time()-step)/60,2),"minutes")
