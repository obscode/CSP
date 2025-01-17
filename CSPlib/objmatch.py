'''Given two sets of coordinates, match up sets of objects'''
import matplotlib
#matplotlib.use('Agg')
from matplotlib import pyplot as plt
from astropy.visualization import simple_norm
from astropy.coordinates import SkyCoord
from astropy import units as u
from numpy import *
from .npextras import bwt 
from .basis import svdfit,abasis
from .sextractor import SexTractor
from .phot import recenter
from astropy.wcs import WCS
from astropy.io import fits

def normalcoord(ra, dec, rc, dc):
   '''Given ra,dec in degrees, convert to normal coordinates.
   
   Args:
      ra (float):  RA in decimal degrees
      dec (float): DEC in decimal degrees
      rc (float):  RA center in decimal degrees
      dc (float):  DEC cneter in decimal degrees.
   
   Returns:
      x,y:  float arrays of normal coordinates
   '''
   ra = ra*pi/180
   dec = dec*pi/180
   rc = rc*pi/180
   dc = dc*pi/180
   squ = cos(dec)*sin(ra-rc)/(sin(dc)*sin(dec)+cos(dc)*cos(dec)*cos(ra-rc))
   eta = (cos(dc)*sin(dec)-sin(dc)*cos(dec)*cos(ra-rc))/\
         (sin(dc)*sin(dec)+cos(dc)*cos(dec)*cos(ra-rc))
   return squ*180/pi, eta*180/pi

def equicoord(u, v, rc, dc):
   '''Given normal coordinates cetered at rc,dc, compute equitorial coords.
   
   Args:
      u (float): normal x coordinate in degrees.
      v (float): normal y coordinate in degrees
      rc (float):  RA center in decimal degrees
      dc (float):  DEC cneter in decimal degrees.

   Returns:
      RA,DEC:  float arrays of equitorial coordinates
   '''
   rc = rc*pi/180
   dc = dc*pi/180
   u = u*pi/180
   v = v*pi/180
   t = u/(cos(dc) - v*sin(dc))
   tt = (sin(dc)+v*cos(dc))/(cos(dc)-v*sin(dc))*cos(arctan(t))
   dec = arctan(tt)
   ra = arctan(t) + rc
   return ra*180/pi,dec*180/pi

def fitscalerot(x0, y0, x1, y1):
   '''compute a scale+rotation transformation.
   
   Args:
      x0 (array):  ra for first set of positions.
      y0 (array):  dec for first set of positions
      x1 (array):  ra for second set of positions.
      y1 (array):  dec for second set of positions
   
   Returns:
      (xshift,yshift,scale,theta,ix,iy,sol)
         xshift,yshift: shift in x/y
         scale:  scale factor between images
         theta:  rotation angle in radians
         ix,iy:  transformed x0, y0
         sol:  the full solution
   '''
   basis = abasis(0, x0, y0, rot=1)
   sol = svdfit(basis, concatenate([x1,y1]))
   ixy = add.reduce(sol[newaxis,:]*basis,1)
   ix,iy = ixy[:len(ravel(x0))], ixy[len(ravel(x0)):]
   theta = arctan2(sol[3],sol[2])
   scale = sol[2]/cos(theta)
   xshift,yshift = sol[0:2]
   return xshift,yshift,scale,theta,ix,iy,sol

def fitpix2RADEC(i, j, x, y):
   '''compute a WCS via CDn_n pixel matrix.i
   
   Args:
      i (array):  pixel coordinates 1
      j (array):  pixel coordinates 2
      x (array):  world cooddinates 1
      y (array):  world coordinates 2
      
   Returns:
      (xshift,yshift, cd11, cd12, cd21, cd22)
   '''
   I = ones(i.shape)
   Z = zeros(i.shape)
   sb = [I, Z, -i, j]
   eb = [Z, I, j, i]
   sb = transpose(sb); eb = transpose(eb)
   basis = concatenate([sb,eb])
   sol = svdfit(basis, concatenate([x,y]))
   xshift,yshift = sol[0:2]
   cd11 = -sol[2]
   cd12 = cd21 = sol[3]
   cd22 = sol[2]
   return xshift,yshift,cd11, cd12, cd21, cd22


def objmatch(x1,y1,x2,y2, dtol, atol, scale1=1.0, scale2=1.0, 
      angles=[0], verb=False):
   '''Given two sets of catalog positions, match the objects.

   Args:
      x1 (array):  x positions of catalog 1
      y1 (array):  y positions of catalog 1
      x2 (array):  x positions of catalog 2
      y2 (array):  y positions of catalog 2
      dtol (float):  distance tolerance for match
      atol (float):  angular tolerance for match
      scale1 (float): plate scale for catalog 1
      scale2 (float): plate scale for catalog 2
      angles (list):  list of angles to try
      verb (bool):  verbose?

   Returns:
      (xshift,yshift,x1, y1, x2, y1):
         xshift,yshift:  the offset from catalog 1 to 2
         x1,y1,x2,y2:  x/y positions of both catalogs ordered to match
   '''

   dx1 = (x1[newaxis,:] - x1[:,newaxis]).astype(float32)*scale1
   dx2 = (x2[newaxis,:] - x2[:,newaxis]).astype(float32)*scale2
   dy1 = (y1[newaxis,:] - y1[:,newaxis]).astype(float32)*scale1
   dy2 = (y2[newaxis,:] - y2[:,newaxis]).astype(float32)*scale2
   da1 = arctan2(dy1,dx1)*180/pi
   da2 = arctan2(dy2,dx2)*180/pi
   ds1 = sqrt(power(dx1,2) + power(dy1,2))
   ds2 = sqrt(power(dx2,2) + power(dy2,2))
   del dx1
   del dx2
   del dy1
   del dy2
   best_N = -1
   best_a = 0
   ds = ds1[:,:,newaxis,newaxis]-ds2[newaxis,newaxis,:,:]
   for aoff in angles:
      da = da1[::,::,newaxis,newaxis] - da2[newaxis,newaxis,::,::] + aoff
      da = where(less(da, -180.0), da+180.0, da)
      da = where(greater(da, 180.0), da-180.0, da)
      use = less(absolute(ds),dtol)*less(absolute(da),atol)
      suse = add.reduce(add.reduce(use,3),1)
      if len(ravel(suse)) == 0 or max(ravel(suse)) < 4: 
         if verb: print("angle {:.2f} gives < 4 matches".format(aoff))
         continue
      guse = greater(suse,max(suse.ravel())//2)
      if verb: print("angle {:.2f} gives {} matches".format(aoff, 
            sum(ravel(guse))))
      if sum(ravel(guse)) > best_N:
         best_a = aoff
         best_N = sum(ravel(guse))
   da = da1[::,::,newaxis,newaxis] - da2[newaxis,newaxis,::,::] + best_a
   da = where(less(da, -180.0), da+180.0, da)
   da = where(greater(da, 180.0), da-180.0, da)
   use = less(absolute(ds),dtol)*less(absolute(da),atol)
   suse = add.reduce(add.reduce(use,3),1)
   guse = greater(suse,max(suse.ravel())//2)
   if verb:
      print("Found {} matches".format(sum(ravel(guse))))
      if best_a != 0:
         print("Best angular offset = {:.2f}".format(best_a))

   i = [j for j in range(x1.shape[0]) if sum(guse[j])]
   m = [argmax(guse[j]) for j in range(x1.shape[0]) if sum(guse[j])]
   xx1,yy1 = take([x1,y1],i,1)
   xx2,yy2 = take([x2,y2],m,1)
   rscale = scale2/scale1
   best_a = best_a*pi/180.0
   xt2 = rscale*(cos(best_a)*xx2 + sin(best_a)*yy2)
   yt2 = rscale*(-sin(best_a)*xx2 + cos(best_a)*yy2)
   xshift,xscat = bwt(xx1-xt2)
   xscat = max([1.0,xscat])
   yshift,yscat = bwt(yy1-yt2)
   yscat = max([1.0,yscat])
   print(xscat,yscat)
   keep = less(absolute(xx1-xt2-xshift),3*xscat)*\
          less(absolute(yy1-yt2-yshift),3*yscat)
   xx1,yy1,xx2,yy2 = compress( keep, [xx1,yy1,xx2,yy2], 1)
   #wt = ones(x0.shape,float32)
   return xshift,yshift,xx1,yy1,xx2,yy2

def iterativeSol(x1, y1, x2, y2, scale1=1.0, scale2=1.0, dtol=1.0, atol=1.0, 
      angles=[0], Niter=3, verb=False):
   '''Using iteration, solve for the transformation from x1,y1 to
   x2,y2, returning the solution and tranformed x1,y1

   Args:
      x1,y1 (float,float):  coordinates to be transformed
      x2,y2 (float,float):  target coordinates
      scale1 (float):  pixel scale of (x1,y1)
      scale2 (float):  pixel scale of (x2,y2)
      dtol (float):  matching distance tolorance in scaled coordinates
      atol (float):  matching angles in degrees
      angles (list of floats):  Try these angle offsets between the two
                                coordinate systems.
      Niter (int):  Number of iterations
      verb (bool):  Be verbose?

   Returns:
      sol,xt,yt:   sol = array of floats, the solution
                   xt,yt = transformed x1, y1
   '''

   # First get matching set
   xshift,yshift,xx1,yy1,xx2,yy2 = objmatch(x1,y1,x2,y2,dtol, atol,
         scale1, scale2, angles, verb)

   if len(xx1) < 3:
      if verb:
         print("Sorry, less than 3 matches found, giving up")
      return None,None,None

   for iter in range(Niter):
      if iter:   # after first iteration
         basis = abasis(0, x1, y1, rot=1)
         ixy = add.reduce(sol[newaxis,:]*basis, 1)
         ix,iy = ixy[:len(ravel(x1))], ixy[len(ravel(x1)):]
         delx = ix[:,newaxis] - x2[newaxis,:]
         dely = iy[:,newaxis] - y2[newaxis,:]
         dels = sqrt(power(delx,2) + power(dely,2))
         ui0 = [j for j in range(delx.shape[0]) if min(dels[j]) < dtol]
         ui1 = [argmin(dels[j]) for j in range(delx.shape[0]) \
                if min(dels[j]) < dtol]
         if len(ui0) == 0:
            if verb:
               print("Error:  residuals of coordinate transformation are all "
                     "greater than dtol")

            return None,None,None
         xx1,yy1 = take([x1, y1], ui0, 1)
         xx2,yy2 = take([x2, y2], ui1, 1)
      if verb:
         print("Pass {} with {} objects.".format(iter+1, len(x1)))
      xshift,yshift,scale,rot,ix,iy,sol = fitscalerot(xx1,yy1,xx2,yy2)
      print(xshift,yshift, scale, rot)
      delx = ix-xx2
      dely = iy-yy2
      dels = sqrt(power(delx,2) + power(dely,2))
      scx = bwt(delx)[1]
      scy = bwt(dely)[1]
      if verb:
         print("Biweight estimate for scatter in coordinate trans: (x,y) ="
            "({:.5f},{:.5f})".format(scx,scy))
   return sol, ui0, ui1


def WCStoImage(wcsimage, image, thresh=3, threshw=3, scale='SCALE', tel='SWO', 
      ins='NC', Nstars=100, deblend_mc=0.005, verbose=False, angles=[0.0], 
      plotfile=None):
   '''Given a FITS image with a WCS, solve for the WCS in a different
   image.

   Args:
      wcsimage (str or FITS):  Image with the WCS
      image (str or FITS):  Image to solve
      scale (str of float): The plate scale of the images to solve.
                            if a string, get scale from the specified 
                            header keyword.
      thresh(float):   Threshold for image source detection
      threshw(float):   Threshold for WCS image source detection
      deblend_mc(float):  Source extractors DEBLEND_MINCONT parameter
      tel (str):   Telescope code (e.g., SWO)
      ins (str):   Instrument code (e.g., NC)
      verbose (bool):  extra debug info?
      plotfile (str):  If specified, plot the WCS solution and save to this file
   Returns:
      The original image with WCS header information updated.

   Note:
      We currently only solve for a shift, scale and rotation
   '''

   if isinstance(wcsimage, str):
      wcsimage = fits.open(wcsimage)
   if isinstance(image, str):
      image = fits.open(image)
   if isinstance(scale, str):
      imscale = image[0].header[scale]
   else:
      imscale = scale

   # get scale from WCS, since we have it
   wcs = WCS(wcsimage[0])
   wscale = abs(wcs.pixel_scale_matrix.max())*3600   # in arc-sex/pixel

   s = SexTractor(image, tel=tel, ins=ins)
   s.run(thresh=thresh, deblend_mc=deblend_mc)
   icat = s.parseCatFile()
   s.cleanup()
   icat = icat[argsort(icat['MAG_APER'])]

   s = SexTractor(wcsimage, tel=tel, ins=ins, gain=1.0, scale=wscale)
   s.run(thresh=threshw, deblend_mc=deblend_mc)
   wcat = s.parseCatFile()
   s.cleanup()
   wcat = wcat[argsort(wcat['MAG_APER'])]

   x1,y1 = wcat['X_IMAGE'],wcat['Y_IMAGE']
   x0,y0 = icat['X_IMAGE'],icat['Y_IMAGE']

   # Get rid of edge cases
   gids0 = (x0 > 10) & (x0 < image[0].data.shape[1]-10) & (y0 > 10) & \
           (y0 < image[0].data.shape[0]-10)
   gids1 = (x1 > 10) & (x1 < wcsimage[0].data.shape[1]-10) & (y1 > 10) & \
           (y1 < wcsimage[0].data.shape[0]-10)

   #icat = icat[:Nstars] 
   #wcat = wcat[:Nstars]
   x0 = x0[gids0][:Nstars]
   y0 = y0[gids0][:Nstars]
   x1 = x1[gids1][:Nstars]
   y1 = y1[gids1][:Nstars]

   if verbose:
      savetxt('matches0.txt', [x0,y0])
      savetxt('matches1.txt', [x1,y1])

   res,idx1,idx2 = iterativeSol(x0, y0, x1, y1, scale1=imscale, scale2=wscale,
         dtol=1.0, verb=verbose, angles=angles)
   if res is None: return None
   ii,ij = take([x0,y0], idx1, 1)  # Source extractor indexes from 1
   wi,wj = take([x1,y1], idx2, 1)

   x,y = wcs.wcs_pix2world(wi,wj,0)
   i0 = image[0].data.shape[1]//2
   j0 = image[0].data.shape[0]//2
   xc,yc = median(x),median(y)
   u,v = normalcoord(x, y, xc, yc)
   # Now solve or CD matrix
   u0,v0,cd11,cd12,cd21,cd22 = fitpix2RADEC(ii-i0, ij-j0, u, v)
   ra0,dec0 = equicoord(u0, v0, xc, yc)

   image[0].header['CTYPE1'] = 'RA---TAN'
   image[0].header['CTYPE2'] = 'DEC--TAN'
   image[0].header['CRPIX1'] = i0
   image[0].header['CRPIX2'] = j0
   image[0].header['CRVAL1'] = ra0
   image[0].header['CRVAL2'] = dec0
   image[0].header['CD1_1'] = cd11
   image[0].header['CD1_2'] = cd12
   image[0].header['CD2_1'] = cd21
   image[0].header['CD2_2'] = cd22

   # Estimate how good we're doing
   nwcs = WCS(image[0])
   # predicted pixels
   pi,pj = nwcs.wcs_world2pix(x,y,1)
   dists = sqrt(power(pi-ii,2) + power(pj-ij,2))
   sig = 1.5*median(dists)
   print("MAD dispersion in WCS determination: {}".format(sig))
   if sig > 5.0:
      print("MAD > 5.0, looks like we failed to converge")
      return None

   if plotfile is not None:
      fig = plt.figure(figsize=(9,9))
      ax = fig.add_subplot(111, projection=nwcs)
      norm = simple_norm(image[0].data, percent=99)
      ax.imshow(image[0].data, origin='lower', norm=norm)
      ii,jj = nwcs.wcs_world2pix(x,y,0)
      ax.plot(ii, jj, 'o', ms=30, mfc='none', mec='red')

      #fig.show_grayscale(invert=True)
      #fig.show_markers(x, y, marker='o', s=30)
      fig.savefig(plotfile)

   return image

def TweakWCS(wcsimage, image, tel='SWO', ins='NC', Nstars=100, verbose=False,
      tol=5):
   '''Given an image with wcs info and another image from the same instrument
   and pointing (next filter, repeated observation, etc), do a WCS solution.
   The expectation is that the stars will not have moved by more than a few
   FWHM in between observations.

   Input:
      wcsimage (fits,str):  The image (or file) with the valid WCS
      image (fits,str):  The image that needs a WCS
      tel,ins (str,str):  The Telescope and instrument codes
      Nstars (int):  Maximum number of stars to solve
      verbose(bool):  Be verbose?
      tol (float):  Tolerance for the std-dev of residuals'''

   # Convert to FITS if needed
   if isinstance(wcsimage, str):
      wcsimage = fits.open(wcsimage)
   if isinstance(image, str):
      image = fits.open(image)

   # Make sure we have rotated
   if 'ROTANG' not in image[0].header:
      image[0].data = image[0].data.T
      image[0].data = image[0].data[:,::-1]
      image[0].header['ROTANG'] = 90

   # First, we get the sources from the wcsimage and their world coords
   s = SexTractor(wcsimage, tel, ins)
   s.run(deblend_mc=1.0)
   wcat = s.parseCatFile()
   wcs = WCS(wcsimage[0])
   wi,wj = wcat['X_IMAGE'],wcat['Y_IMAGE']
   wx,wy = wcs.wcs_pix2world(wi,wj, 1)

   # Now recenter on the target image
   ii,ij,flags = recenter(wi, wj, image[0].data, method='com')

   gids = equal(flags, 0)
   if sum(gids) < 5:
      print("Not enough good stars")
      return None

   i0 = image[0].data.shape[1]//2
   j0 = image[0].data.shape[0]//2
   xc,yc = median(wx[gids]),median(wy[gids])
   u,v = normalcoord(wx[gids], wy[gids], xc, yc)

   u0,v0,cd11,cd12,cd21,cd22 = fitpix2RADEC(ii[gids]-i0, ij[gids]-j0, u, v)
   ra0,dec0 = equicoord(u0, v0, xc, yc)

   image[0].header['CTYPE1'] = 'RA---TAN'
   image[0].header['CTYPE2'] = 'DEC--TAN'
   image[0].header['CRPIX1'] = i0
   image[0].header['CRPIX2'] = j0
   image[0].header['CRVAL1'] = ra0
   image[0].header['CRVAL2'] = dec0
   image[0].header['CD1_1'] = cd11
   image[0].header['CD1_2'] = cd12
   image[0].header['CD2_1'] = cd21
   image[0].header['CD2_2'] = cd22

   # Estimate how good we're doing
   nwcs = WCS(image[0])
   # predicted pixels
   pi,pj = nwcs.wcs_world2pix(wx[gids],wy[gids],1)
   dists = sqrt(power(pi-ii[gids],2) + power(pj-ij[gids],2))
   sig = 1.5*median(dists)
   print("MAD dispersion in WCS determination: {}".format(sig))
   if sig > tol:
      print("MAD > {} looks like we failed to converge".format(tol))
      return None

   return image

def FindIsolatedStars(stab, cat, wcs, mindist, Nmin):
   ''' Given a table of sources from SourceFinder and a catalog of calibration
   stars, find isolated ones (min sep > mindist).
   
   Args:
      stab (astroy.table):  table of detected sources. Must have X_IMAGE,Y_IMAGE,
                           and MAG_BEST columns.
      cat (astropy.table):  table of catalog sources. Must have 'RA' and 'DEC'
                            columns.
      wcs (astropy.coordinates):  The wcs of the image from which sources were
                            detected
      mindist (float):  minimum separation of sources (ideally outside sky annulus)
                        in arc-sec
      Nmin (int):  Minimum number of sources we want. If not enough separated ones,
                   then we give back ones with minimal flux-ratio.
      scale(float):  pixel scale
      rmax(float):  radius to within which we consider stars for flux ratio limit
   '''
   # Right off get rid of close pairs of catalog objects
   dists = power((cat['RA'][:,newaxis]-cat['RA'][newaxis,:])*cos(cat['DEC']*pi/180),2) +\
           power((cat['DEC'][:,newaxis]-cat['DEC'][newaxis,:]),2)
   dists = sqrt(dists)*3600
   Nnn = sum(less(dists, mindist), axis=0)
   gids = equal(Nnn, 1)
   cat = cat[gids]
   # First, figure out the pixel locations of the catalog sources and RA/DEC of the
   #  detected sources
   i,j = wcs.wcs_world2pix(cat['RA'],cat['DEC'], 0)
   ra,dec = wcs.wcs_pix2world(stab['X_IMAGE'], stab['Y_IMAGE'], 0)

   c1 = SkyCoord(cat['RA'], cat['DEC'], unit=(u.degree,u.degree))
   c2 = SkyCoord(ra, dec, unit=(u.degree, u.degree))
   idx,sep,sep2d = c1.match_to_catalog_sky(c2)
   # Find the catalog objects within the frame and corresponsing detections
   gids = less(sep.to(u.arcsec).value, 0.5)   # less than 0.5 arc-second
   cat = cat[gids]
   print(len(cat))
   i = i[gids]
   j = j[gids]
   c1 = c1[gids]
   idx = idx[gids]
   # remove corresponding source detections
   hits = array([i in idx for i in range(len(stab))])
   mags = stab[idx]['MAG_BEST']
   stab = stab[~hits]

   # Next, we find distances between catalog sources and detected sources
   # dists[i,j] = distance between catalog object i and detected object j
   dists = sqrt((i[:,newaxis]-stab['X_IMAGE'][newaxis,:])**2 + \
                (j[:,newaxis]-stab['Y_IMAGE'][newaxis,:])**2)

   # Minimum distances:
   mdists = dists.min(axis=1)*wcs.pixel_scale_matrix.max()*3600
   cat['good'] = mdists > mindist

   # If we have enough, we're done!
   if sum(cat['good']) >= Nmin:
      return cat

   # Okay, not enough. Let's compute the maximum flux ratio of objects within 
   #   mindist
   maxfluxrats = []
   for i in range(len(cat)):
      if cat[i]['good']: 
         maxfluxrats.append(-1)
         continue
      rids = dists[i] < mindist
      if not any(rids):
         cat[i]['good'] = True
         maxfluxrats.append(-1)
         continue
      fluxrats = power(10, -0.4*(stab[rids]['MAG_BEST']-mags[i]))
      if all(fluxrats < 0.01): cat[i]['good'] = True
      maxfluxrats.append(fluxrats.max())
   
   if sum(cat['good']) > Nmin: return cat

   # Okay, not all sources are clean. Get to Nmin by giving the minimum maxfluxrat
   N = sum(cat['good'])
   sids = argsort(maxfluxrats)
   for i in sids:
      if cat[i]['good']: continue
      cat[i]['good'] = True
      N += 1
      if N >= Nmin: break
   
   # finally done
   return cat