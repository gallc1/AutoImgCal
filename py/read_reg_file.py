##############################################################################
# PYTHON 3.
#
# FILE:  read_reg_file.py
# AUTOR: Christa Gall
# AFFILIATION: DARK
# DATE:  September 2017
#
# Development environment: Anaconda 2, py36
#-----------------------------------------------------------------------------
# PURPOSE: 
# To read the MAGS from .reg file
#
##############################################################################

import numpy as np 
from numpy import *
from astropy.io import fits
from astropy.time import Time
import string
import os
import pickle
import sys
import glob
import shutil

#----------------------------------------------------------------------------------
# define variables
#----------------------------------------------------------------------------------
def PARLIST():
    PATHTOFILES = '/Users/christagall/Dropbox/PROJECT_SN2017eaw/DATA/PHOTO/NOTCAM/H_calib/'
    #PATHTOFILES = '/Users/christagall/Dropbox/PROJECT_SN2017eaw/DATA/PHOTO/NOTCAM/J_calib/'
    #PATHTOFILES = '/Users/christagall/Dropbox/PROJECT_SN2017eaw/DATA/PHOTO/NOTCAM/K_calib/'
    #PATHTOFILES = os.getcwd()+'/'
    INFLSERCH = ['*obj_im.reg', '*calibrated.fits']
    AUTOREAD = 'Y'      #[Y, N]

    PIXPOS = [685.500, 711.750]
    PIXTOL = [5.0, 6.0]

    #list the date for the MAGs.txt file as JD or MJD
    DATE = 'JD'         #[JD, MJD]
    
    PARLIST = [PATHTOFILES, INFLSERCH, AUTOREAD, PIXPOS, PIXTOL, DATE]
    return PARLIST
#----------------------------------------------------------------------------------
# define functions
#----------------------------------------------------------------------------------

def READ_FILE_NAME():
    FILENAME = input('Please enter the Filename = ')
    print(FILENAME)
    return FILENAME
    
def GET_FNUM(x):
    return float(''.join(ele for ele in x if ele.isdigit() or ele == '.'))
    
def READ_WRITE_FILES(FILENAME):
    f=open(FILENAME, 'r')
    HEADER=f.readlines()[0:3]
    HNUM=len(HEADER)
    f.close
    f=open(FILENAME, 'r') 
    F=f.readlines()[4:]
    FNUM=len(F)
    
    COL1=[]
    COL2=[]
    COL3=[]
    COL4=[]
    for line in F:       
        L=line.split()
        L1=L[0].split(',',1)
        P=len(L)
        P1=len(L1)
        COL1.append(GET_FNUM(L1[0]))
        COL2.append(GET_FNUM(L1[1]))
        COL3.append(GET_FNUM(L[3]))
        COL4.append(GET_FNUM(L[5]))
    f.close()
    
    fout=open(FILENAME+'.txt','w')
    for i in range(HNUM):
        fout.write(HEADER[i])
    for i in range(FNUM):
        fout.write('{:10.3f}{:10.3f}{:8.3f}{:8.3f}\n'.format(COL1[i],COL2[i],COL3[i],COL4[i]))
    fout.close

    return [COL1,COL2,COL3,COL4]
    

def GET_MAG(COLS):
    PARA=PARLIST()
    CNUM  = len(COLS[0])
    for i in range(2):
        COL1  = array(COLS[i])
        TOLOW = PARA[3][i]-PARA[4][i]
        TOUP  = PARA[3][i]+PARA[4][i]
        IN   = np.where((COL1[0:] > TOLOW) & (COL1[0:] < TOUP))[0]
        if i==0:
            IND1=IN
        if i==1:
            IND2=IN
    print('IN', IND1, IND2)
                
    A1=len(IND1)
    A2=len(IND2)
#    print('len', A1, A2)
    if A1==0 or A2==0: 
        sys.exit('!WARNING! No matching indices have been found, please increase the pixel range')
        
    for i in range(A1):
        for j in range(A2):
#            print(IND1[i],IND2[j])
            if IND1[i]==IND2[j]:
                INDF=IND1[i]
                
    B1 = COLS[2][INDF]
    B2 = COLS[3][INDF]             
    return [B1,B2]

def GET_OBSDATE(FILENAME):
    FITSFILE = fits.open(FILENAME)
    DATE = FITSFILE[0].header['DATE-OBS']
#    print(DATE)
    
    T = Time(DATE, format='isot', scale='utc')
    JDATE  = T.jd
    MJDATE = T.mjd    
    return [JDATE, MJDATE]



def READ_REG_FILE():
    PARA=PARLIST()
    MAG=[]
    DATE=[]
    if PARA[2] == 'Y': 
        REGFILELIST  = glob.glob(PARA[0]+PARA[1][0])
        FITSFILELIST = glob.glob(PARA[0]+PARA[1][1])
    elif PARA[2] == 'N':
        REGFILELIST[0]  = READ_FILE_NAME() 
        FITSFILELIST[0] = READ_FILE_NAME()        
        
    for FNAME in REGFILELIST: 
        COLS = READ_WRITE_FILES(FILENAME=FNAME)
        MAG_NEW = GET_MAG(COLS)
        MAG.append(MAG_NEW)
        
    for FNAME in  FITSFILELIST:
        DATE_NEW = GET_OBSDATE(FILENAME=FNAME)
        DATE.append(DATE_NEW)
        
        
    print('mag', MAG)
#    print(len(MAG))
    fout=open(PARA[0]+'MAGs.txt','w')
    for i in range(len(MAG)):
        if PARA[5]=='JD':
            fout.write('{:10.3f}{:10.3f}{:10.3f}\n'.format(DATE[i][0],MAG[i][0],MAG[i][1]))
        elif PARA[5]=='MJD':
            fout.write('{:10.3f}{:10.3f}{:10.3f}\n'.format(DATE[i][1],MAG[i][0],MAG[i][1]))        
    fout.close

#----------------------------------------------------------------------------------
# actually run the code    
#----------------------------------------------------------------------------------

def main():

    print ('\n Start of program to get the MAG of your object from the .reg file.\n \n Please check your settings NOW : \n') 
    PARA=PARLIST()
    print(' Current path to your files: ', PARA[0])
    print('\n You are reading files automatically from list: ', PARA[2])
    if PARA[2]=='Y':
        print('\n You are listing following files: ', PARA[1][0], ' and ', PARA[1][1])
    else: 
        print('\n You are reading one file through commandline: ', PARA[2])
    print('\n You are searching for postion: ', PARA[3][0], ',',PARA[3][1], 'within a range ', PARA[4][0], ',', PARA[4][0])
    
    SWITCH = input('\n To continue press [enter], to stop and change parameters press [p]: ')
    if SWITCH=='p':
        sys.exit('Please check your parameter settings')
    
    READ_REG_FILE()
    
if __name__=='__main__':
    main()

#==================================================================================
#                                              END
#==================================================================================

    