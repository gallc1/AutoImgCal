#!/usr/bin/env python

# NOT FOR PRODUCTION USE.

#
# Authors: Thomas Kruehler, Abdullah Yoldas, Sebastian Jester <kruehler@mpe.mpg.de, yoldas@mpe.mpg.de, jester@mpia.de>
# Based on i_usnob1.py by Abdullah Yoldas <yoldas@mpe.mpg.de>

# 2010-05-25 yoldas Set a timeout for wget, catch OSError for output
# 2010-10-17 yoldas Use Vizier for SDSS if the CAS SDSS query fails.
# 2010-10-17 yoldas Prevent downloading the catalogs twice.
# 2011-01-11 kruehler Using dr8/9 for CAS queries
# 2013-07-29 kruehler Add APASS option
# 2016-09-22 kruehler Add Gaia option
# 2016-12-19 kruehler Add Pan-Starrs

"""
Retrieve  objects from SDSS or APASS (directly) or USNOA2/B1 via Vizier.
Depends on sqlcl.py obtainable from http://cas.sdss.org/dr7/en/help/download/sqlcl/
Usage: grb_cat.py options
Options:
    -c  <ra_in_deg><dec_in_deg> ra and dec coordinates in degrees
    -r  <rad_in_arcmin>         radius in arcminutes
    -s  <catalog>               desired catalog (SDSS, USNOB1, 2MASS, DENIS, PS)
    -b  <band>                  desired band (must exist in requested catalog)
    -f  <output_file>           output file (default is standard output)

There cannot be any white space between coordinates (use + or - to separate).
Output is sorted by distance to the center in following format:
ra_in_deg\tdec_in_deg\tImag\te_Imag
"""

import getopt
import sys
import urllib.request
import urllib.parse
import tempfile
import os
import socket
import signal
import numpy as np
import subprocess
from socket import setdefaulttimeout

setdefaulttimeout(30)


class Alarm(Exception):
    pass


def alarm_handler(signum, frame):
    raise Alarm


def get_options():
    """Parse options. As a reminder, they are:
    Options:
    -c   <ra_in_deg><dec_in_deg> ra and dec coordinates in degrees
    -r   <rad_in_arcmin>         radius in arcminutes
    -s   <catalog>               desired catalog (SDSS, USNO, DENIS, 2MASS,
                                                 APASS, GAIA, PS)
    -b   <band>                  desired band (must exist in requested catalog)
    -f   <output_file>           output file (default is standard output)
    -d   <ds9 region_file>       prodice region file (default is none)

    """
    rad = filename = cat = band = hawki = regionname = None
    try:
        optlist, args = getopt.getopt(sys.argv[1:], 'c:r:f:s:b:h:d:')
        for o, v in optlist:
            if o == '-c':
                if len(v.split('+')) == 2:
                    ra = v.split('+')[0]
                    dec = v.split('+')[1]
                elif len(v.split('-')) == 2:
                    ra = v.split('-')[0]
                    dec = '-'+v.split('-')[1]
                else:
                    raise ValueError('Invalid coordinate format.')

            elif o == '-r':
                # convertible to float? (int is ok, too)
                float(v)
                rad = v
            elif o == '-f':
                # if filename is specified, create.
                filename = open(v, 'w')
            elif o == '-d':
                # if filename is specified, create.
                regionname = open(v, 'w')
            elif o == '-s':
                cat = v.upper()
            elif o == '-b':
                band = v
            elif o == '-h':
                hawki = 1

        if hawki == 1:
            rad = '3.9'
            cat = '2MASS'

        if rad is None:
            raise ValueError('radius must be specified.')
#        print(cat

        if cat not in ['GAIA', 'SDSS','USNO','2MASS', 'DENIS', 'APASS', 'PS']:
            raise ValueError("""catalog must be specified and one of Gaia,
            SDSS, USNO, 2MASS, DENIS, APASS, PS""")

        DENISbands = 'IJK'
        SDSSbands = 'ugriz'
        USNObands = 'BRI'
        twoMASSbands = 'JHK'
        APASSbands = 'BVgri'
        GaiaBands = 'G'
        PSbands = 'grizy'

        if cat == "PS" and band not in set(PSbands):
            raise ValueError('For -s PS band needs to be one of '+PSbands)
        if cat == "SDSS" and band not in set(SDSSbands):
            raise ValueError('For -s SDSS band needs to be one of '+SDSSbands)
        if cat == "USNO" and band not in set(USNObands):
            raise ValueError('For -s USNO band needs to be one of '+USNObands)
        if cat == "2MASS" and band not in set(twoMASSbands):
            raise ValueError('For -s 2MASS band needs to be one of '+twoMASSbands)
        if cat == "DENIS" and band not in set(DENISbands):
            raise ValueError('For -s DENIS band needs to be one of '+DENISbands)
        if cat == "APASS" and band not in set(APASSbands):
            raise ValueError('For -s APASS band needs to be one of '+APASSbands)
        if cat == "GAIA" and band not in set(GaiaBands):
            raise ValueError('For -s Gaia band needs to be one of '+GaiaBands)

        if filename is None:
            # No filename is specified, we will write to stdout.
            filename = sys.stdout

    except (getopt.GetoptError):#, ValueError, TypeError, EnvironmentError):
        print(__doc__)
        t, v = sys.exc_info()[:2]
        sys.stderr.write('ERROR: %s: %s\n' % (t, v))
        sys.exit(2)

    return ra, dec, rad, filename, cat, band, hawki, regionname


def get_SDSS_runcamfield(ra,dec,release="dr12"):
    """Retrieve run, camcol, field from SDSS."""
    ra, dec = sexa2deg(ra, dec)

    urls = [
        'http://skyserver.sdss.org/%s/en/tools/search/x_sql.aspx' % (release),
            'http://cas.sdss.org/dr9/en/tools/search/x_sql.asp',]

    for url in urls:
        run, camcol, field, result = '', '', '', ''
        # Should add some basic flag checking to this query template.
        query_template = """select p.run, p.camcol, p.field from STAR as p
        inner join dbo.fGetNearbyObjEq(%s,%s,%s) as N on p.objid = N.objid"""
        query = query_template % (ra, dec, 1)
        signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(5)
        try:
            args = ['sqlcl.py', '-l', '-q', '%s' % query,
                    '-s', '%s' % url, '-f', 'csv']
            proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            result = proc.stdout.readlines()
            signal.alarm(0)
        except Alarm:
            pass
        except:
            raise RuntimeError("Could not run sqlcl.py")
# =============================================================================
#   Remove first entry in list if coming from skyserver query
# =============================================================================
        if 'run,camcol,field\n' in result:
            result.remove('run,camcol,field\n')

        if len(result) > 0:
            try:
                [run, camcol, field] = result[0].split(',')[0:3]
                break
            except IndexError:
                pass

    return run, camcol, field


#==============================================================================
# Coordinate converstions
#==============================================================================


def isnumber(num):
    try:
        float(num)
        return True
    except ValueError:
        return False


def addzero(val, n):
    if isnumber(val):
        val = float(val)
        if n == 1: valr = '%.0f' %val
        if n == 2: valr = '%.2f' %val
        if n == 3: valr = '%.3f' %val
        if float(val) < 10:
            if n == 1: valr = '0%.0f' %val
            if n == 2: valr = '0%.2f' %val
            if n == 3: valr = '0%.3f' %val
    return valr


def sexa2deg(ra, dec):
    if isnumber(ra):
        retra = ra
    else:
        ra = ra.split(':')
        retra = (float(ra[0])+float(ra[1])/60.+float(ra[2])/3600.)*15

    if isnumber(dec):
        retdec = dec
    else:
        dec = dec.split(':')
        if dec[0][0] == '-':
            retdec = float(dec[0])-float(dec[1])/60.-float(dec[2])/3600.
        else:
            retdec = float(dec[0])+float(dec[1])/60.+float(dec[2])/3600.
    return round(float(retra), 6), round(float(retdec), 6)


def deg2sexa(ra, dec):
    retra = ra
    if isnumber(ra):
        ra = float(ra)
        hours = int(ra/15)
        minu = int((ra/15.-hours)*60)
        seco = float((((ra/15.-hours)*60)-minu)*60)
        retra = '%s:%s:%s' % (addzero(hours, 1),
                              addzero(minu, 1), addzero(seco, 3))
    retdec = dec
    if isnumber(dec):
        dec = float(dec)
        degree = int(dec)
        minutes = int((dec-degree)*60)
        seconds = float((((dec-degree)*60)-minutes)*60)
        if dec < 0:
            retdec = '-%s:%s:%s' % (addzero(-1*degree, 1),
                                    addzero(-1*minutes, 1),
                                    addzero(-1*seconds, 2))
        else:
            retdec = '+%s:%s:%s' % (addzero(degree, 1),
                                    addzero(minutes, 1),
                                    addzero(seconds, 2))
    return retra, retdec


def dist(ra1, dec1, ra2, dec2):
    ra1, dec1 = np.radians(float(ra1)), np.radians(float(dec1))
    ra2, dec2 = np.radians(float(ra2)), np.radians(float(dec2))
    dra, ddec = (ra2 - ra1), abs(dec2 - dec1)
    d1 = 2.*np.arcsin(np.sqrt((np.sin(ddec/2.))**2 +
            np.cos(dec1)*np.cos(dec2)*(np.sin(dra/2.))**2))
    d2 = d1 * 180./np.pi
    return d2

#==============================================================================
# Main driver method
#==============================================================================

def main():

    """Driver routine that calls the correct subroutine depending on catalog"""
    ra, dec, radius, filename, catalog, band, hawki, regionname = get_options()
    ra, dec = sexa2deg(ra, dec)
    lines = []
    bandmatch = {'g': 'B', 'r':'R', 'i': 'I', 'z': 'I', 'u':'B', 'G':'R'}

    if catalog == 'PS':
        if ra < -30:
            print("Couldn't query Pan-Starrs, falling back to SDSS")
            catalog, band = 'SDSS', bandmatch[band]
        else:
            lines = get_PS(ra, dec, radius, band)
            if lines == []:
                print("Couldn't query Pan-STARRS, falling back to USNO")
                catalog, band = 'USNO', bandmatch[band]

    if catalog == 'SDSS':
        run, camcol, field = get_SDSS_runcamfield(ra, dec)

        if [run, camcol, field] == ['', '', '']:
            if band in 'gri':
                print("Not SDSS covered, trying APASS for GROND "+band)
                catalog = 'APASS'
        else:
            print("SDSS covered, querying SDSS")
            try:
                lines = get_SDSS(ra, dec, radius, band)
                print("SDSS query successfull, using SDSS")
            except IOError:
                print("Couldn't query SDSS, falling back to USNO")
                catalog, band = 'USNO', bandmatch[band]

    if catalog == 'APASS':
        lines = get_Vizier(ra, dec, radius, band, catalog)
        if lines == []:
            print("Couldn't query APASS, falling back to USNO")
            catalog, band = 'USNO', bandmatch[band]

    if catalog == 'GAIA':
        lines = get_Vizier(ra, dec, radius, band, catalog)
        if lines == []:
            print("Couldn't query Gaia, falling back to USNO")
            catalog, band = 'USNO', bandmatch[band]

    if catalog == 'DENIS':
        lines = get_Vizier(ra, dec, radius, band, catalog)
        if lines == []:
             if band == 'I':
                 print("DENIS did not return anything, trying USNO for "+band)
                 catalog = 'USNO'
             if band in 'JK':
                 # If DENIS doesn't work, try USNO instead for NIR bands...
                 print("DENIS did not return anything, trying 2MASS for "+band)
                 catalog = '2MASS'

    if catalog in ['USNO', '2MASS']:
        lines = get_Vizier(ra, dec, radius, band, catalog)
        if lines == []:
            raise IOError('Could not retrieve Vizier catalog')
        if hawki == 1:
            maxmag = 20
            for line in lines:
                if float(line.split()[2]) < maxmag:
                    maxra, maxdec = float(line.split()[0]), float(line.split()[1])
                    maxmag = float(line.split()[2])
    if regionname != None:
        regionname.write('global color=red\n')
        for line in lines:
            line = line.split()
            regionname.write("fk5; circle(%.6f,%.6f,4p)\n" \
            %(float(line[0]), float(line[1])))
        regionname.close()


    lines = ''.join(lines)
    filename.write(lines)
    filename.flush()

    print(catalog)

    if hawki == 1:
        print('Brightest source at %s with %.2f mag' %(deg2sexa(maxra, maxdec), maxmag))
        print('Distance = %.1f arcmin' %(dist(ra, dec, maxra, maxdec)*60))


def get_PS(ra, dec, radius, band, ndet=10):
    # MAST mirrors
    mirrors = ['http://archive.stsci.edu/panstarrs/search.php',
               'http://archive.stsci.edu/panstarrs/search.php']

    params = [('RA', '%.4f' %ra),
              ('DEC', '%.4f' %dec),
              ('max_records', 1000),
              ('radius', '%s' %(float(radius))),
              ('outputformat', 'TSV'),
              ('selectedColumnsCsv',
                   'raMean,decMean,%sMeanApMag,%sMeanApMagErr' %(band, band)),
              ('nDetections', '>%i' %ndet),
              ('action', 'Search'),]

    data = urllib.parse.urlencode(params, 1).encode("utf-8")
    i = 0
    saved_timeout = socket.setdefaulttimeout(45)


    while i < len(mirrors):
        try:
            url = mirrors[i]
            try:
                fp = urllib.request.urlopen(url, data)
                lines = [x.decode('utf8').strip() for x in fp.readlines()]
                fp.close()
            except (OSError, IOError):
                t, v = sys.exc_info()[:2]
                if i + 1 == (len(mirrors)):
                    sys.stderr.write('ERROR: %s: %s\n' % (t, v))
#                    sys.exit(1)
                else:
                    sys.stderr.write('WARNING: %s: %s\n' % (t, v))
            i += 1
        finally:
            socket.setdefaulttimeout(saved_timeout)

    output = []
    for p in lines:
        p = p.split('\t')
        if len(p) == 4 and p[0] != '' and float(p[2]) > 0:
            output.append(p)
    result = ['\t'.join(x) for x in output]
    return result


def get_SDSS(ra, dec, radius, band, release="dr12"):
    """Retrieve object list from SDSS. Radius is in arcminutes. Try CAS
    server and then Vizier mirrors."""
    result = []
    try:
        result = get_SDSS_cas(ra, dec, radius, band, release)
    except:
        pass

    if result == []:
        result = get_SDSS_Vizier(ra, dec, radius, band)
    return result


def get_Vizier(ra, dec, radius, band, catalog):
    # VizieR mirrors
    mirrors = [
        'http://vizier.u-strasbg.fr/viz-bin/asu-tsv',
        'http://vizier.cfa.harvard.edu/viz-bin/asu-tsv',
        'http://vizier.nao.ac.jp/viz-bin/asu-tsv',
        'http://vizier.hia.nrc.ca/viz-bin/asu-tsv',
        'http://archive.ast.cam.ac.uk/viz-bin/asu-tsv',
        'http://urania.iucaa.ernet.in/viz-bin/asu-tsv',
        'http://data.bao.ac.cn/viz-bin/asu-tsv',
        'http://www.ukirt.jach.hawaii.edu/viz-bin/asu-tsv']
    if dec > 0: sign = '+'
    else: sign = ''
    # Common params
    params = [('-to', '4'),
        ('-from', '-2'),
        ('-this', '-2'),
        ('-out.max', '682666'),
        ('-out.form', 'Tab-Separated-Values'),
        ('-order', 'I'),
        ('-c', '%.3f%s%.3f'%(ra,sign,dec)),
        ('-c.eq', 'J2000'),
        ('-oc.form', 'dec'),
        ('-c.bm', '%sx%s'%(2*float(radius),2*float(radius))),
        #('-c.u', 'arcmin'),
        #('-c.geom', 'r'),
        ('-sort', '_r'),
        ('-out', 'RAJ2000'),
        ('RAJ2000', ''),
        ('-out', 'DEJ2000'),
        ('DEJ2000', ''),
        ('-file', '.'),
        ('-meta', '2')]

    # Pick catalog according to band

    if (band == 'G') and (catalog == 'GAIA'):
        params +=  [('-source', 'I/337/gaia'),
            ('-out', '<Gmag>'), ('<Gmag>', ''),
            ('-out.add' ,'_RAJ,_DEJ')]

    elif catalog == 'APASS':
         params +=  [('-source', 'II/336/apass9'),
            ('-out', "%s'mag" %band), ("%s'mag"%band, ''),
            ('-out', "e_%s'mag"%band), ("e_%s'mag"%band, ''),
            ]

    elif (band == 'I') and (catalog == 'USNO'):
        params +=  [('-source', 'I/284/out'),
            ('-out', 'Imag'), ('Imag', '')]

    elif band == 'R' and (catalog == 'USNO'):
        params +=  [('-source', 'I/284/out'),
            ('-out', 'R2mag'), ('R2mag', '')]

    elif band == 'B' and (catalog == 'USNO'):
        params +=  [('-source', 'I/284/out'),
            ('-out', 'B2mag'), ('B2mag', '')]

    elif band in 'JHK' and (catalog == '2MASS'):
        bandstr = band +'mag'
        banderr = 'e_'+bandstr
        params += [('-source', 'II/246/out'),
            ('-out', bandstr), (bandstr, ''),
            ('-out', banderr), (banderr, '')]

    elif band == 'I' and (catalog == 'DENIS'):
        bandstr = 'Imag'
        banderr = 'e_'+bandstr
        params += [('-source', 'B/denis/denis'),
            ('-out', bandstr), (bandstr, ''),
            ('-out', banderr), (banderr, '')]

    elif band in 'JK' and (catalog == 'DENIS'):
        bandstr = band +'mag'
        banderr = 'e_'+bandstr
        params += [('-source', 'B/denis/denis'),
            ('-out', bandstr), (bandstr, ''),
            ('-out', banderr), (banderr, '')]

    data = urllib.parse.urlencode(params, 1).encode("utf-8")
    i, j, succ = 0, len(mirrors), 0

    while i < j:
        if succ == 0:
            try:
                urlstring = "'%s?%s'" %(mirrors[i],data)
                tmpfile = tempfile.mktemp('.tsv', 'usnob_data', '/tmp')
                #os.system("wget -q -O %s %s" % (tmpfile,urlstring))

                cmd = "wget -q --timeout 20 --tries 1 -O %s %s" % (tmpfile,urlstring)
#                print(urlstring
                os.system(cmd)
                tmpf = open(tmpfile)
                content = tmpf.readlines()
                tmpf.close()
                os.remove(tmpfile)
                if len(content) > 1:
                    for c in content:
                        if not c.startswith('#'):
                            succ = 1
            except (IOError, OSError):
                t, v = sys.exc_info()[:2]
                if i + 1 == j:
                    sys.stderr.write('ERROR: %s: %s\n' % (t, v))
                    sys.exit(-1)
                else:
                    sys.stderr.write('WARNING: %s: %s\n' % (t, v))
        i += 1
    lines = content

    # skip headers
    j, i = len(lines), 0
    while i < j:
        if lines[i].startswith('---'):
            break
        i += 1
    i += 1
    output = []
    while i < j:
        if lines[i][:3].strip() == '':
            break
        # Split by tabs, and strip individual columns.
        L = map(lambda x: x.strip(), lines[i].split('\t'))
        # If no magnitude is retrieved ignore this object.
        if L[2] == '':
            i += 1
            continue
        L.append('')
        line = '\t'.join(L)
        output.append(line+"\n")
        i += 1
    return output

def get_SDSS_Vizier(ra, dec, radius, band, release = "dr9"):
    """Retrive object list from SDSS. Use Vizier mirrors. ra and dec are
    in degrees, radius is in arcminutes, band is one of (g,r,i,z,u),
    release is always dr9 (V/139/sdss9) is used for the -source param).
    """
    # VizieR mirrors
    mirrors = ['http://vizier.u-strasbg.fr/viz-bin/asu-tsv',
        'http://vizier.nao.ac.jp/viz-bin/asu-tsv',
        'http://vizier.hia.nrc.ca/viz-bin/asu-tsv',
        'http://archive.ast.cam.ac.uk/viz-bin/asu-tsv',
        'http://urania.iucaa.ernet.in/viz-bin/asu-tsv',
        'http://data.bao.ac.cn/viz-bin/asu-tsv',
        'http://vizier.cfa.harvard.edu/viz-bin/asu-tsv',
        'http://www.ukirt.jach.hawaii.edu/viz-bin/asu-tsv']

    if dec > 0: sign = '+'
    else: sign = ''
    params = [('mode', 1),
        ('cl', '6'),
        ('-out.max', '682666'),
        ('-out.form', 'Tab-Separated-Values'),
        ('-order', 'I'),
        ('-c', '%.3f%s%.3f'%(ra,sign,dec)),
        ('-c.eq', 'J2000'),
        ('-oc.form', 'dec'),
        ('-c.bm', '%sx%s'%(2*float(radius),2*float(radius))),
        ('-c.u', 'arcmin'),
        #('-c.geom', 'r'),
        ('-sort', '_r'),
        #('-out', 'objID'),     # used in checking the outputs
        ('-out', 'RAJ2000'),
        ('RAJ2000', ''),
        ('-out', 'DEJ2000'),
        ('DEJ2000', ''),
        ('-source', 'V/139/sdss9'),
        ('-out', '%smag' % band),
        ('-out', 'e_%smag' % band),
        ('e_%spmag' % band, '<= 0.18'),
        ('-out', '%ss' % band), # from the SQL query
        ('-out', 'flags')]

    data  = urllib.parse.urlencode(params, 1).encode("utf-8")
    n, i = len(mirrors), 0
    saved_timeout = socket.setdefaulttimeout(20)
    try:
        while i < n:
            url = mirrors[i]
            try:
                fp = urllib.request.urlopen(url, data)
                lines = fp.readlines()
                fp.close()
                break
            except (OSError, IOError):
                t, v = sys.exc_info()[:2]
                if i + 1 == n:
                    sys.stderr.write('ERROR: %s: %s\n' % (t, v))
                    sys.exit(1)
                else:
                    sys.stderr.write('WARNING: %s: %s\n' % (t, v))
            i += 1
    finally:
        socket.setdefaulttimeout(saved_timeout)

    # Skip headers
    n, i = len(lines), 0
    while i < n:
        if lines[i].startswith('---'):
            break
        i+= 1
    i += 1
    lines = lines[i:]
    # Filter using the masks in the original SQL query:
    try:
        output = []
        i = 0
        for p in lines:
            p = p.split('\t')
            try:
                flags = int(p[-1], 16)  # hex
            except:
                continue
            if (((flags & 0x10000000) != 0 and
                (flags & 0x8100000c00a4) == 0 and
                (flags & 0x400000000000) == 0 and
                (flags & 0x400000000000) == 0 and
                ((flags & 0x100000000000) == 0) or
                   (flags & 0x1000) == 0)):
             #           pass
            #if int(p[-2]) == 1:
                output.append(p[:-2])
    except:
        import traceback
        traceback.print_exc()
    # Join the columns back; The output is expected as a list of lines.
    lines = ['\t'.join(x)+'\n' for x in output]
    return lines

def get_SDSS_cas(ra, dec, radius, band, release="dr12"):
    """Retrieve object list from SDSS. Radius is in arcminutes."""
#    url = 'http://skyserver.sdss3.org/%s/en/tools/search/x_sql.asp' % (release)
    url = "http://cas.sdss.org/dr9/en/tools/search/x_sql.asp" #% (release)
    query_template = "select p.ra, p.dec, p.%s, p.Err_%s from STAR as p \
inner join dbo.fGetNearbyObjEq(%s,%s,%s) as N on p.objid = N.objid \
where ((p.flags & 0x10000000) != 0) \
AND ((p.flags & 0x8100000c00a4) = 0) \
AND (((p.flags & 0x400000000000) = 0) AND (p.psfmagerr_%s <= 0.18)) \
AND (((p.flags & 0x100000000000) = 0) or (p.flags & 0x1000) = 0)"
    query = query_template % (band, band, ra, dec, radius, band)
    # To get also the magnitude error, add p.Err_%s to the select
    # clause, and dchange the % string to (band, band, ...)
    try:
#        print("sqlcl.py -l -q \"%s\" -s %s -f csv" %(query,url)
        result = os.popen("sqlcl.py -l -q \"%s\" -s %s -f csv" %(query,url)).readlines()
        # Replace commas by tabs to match the USNO routine's output format
        result = map(lambda l: l.replace(',','\t'),result)
    except:
        raise RuntimeError("Could not run sqlcl.py")
    return result

if __name__ == '__main__':
    main()
