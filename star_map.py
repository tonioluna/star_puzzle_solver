import argparse
import math
import sys
import os
import time
import types
import random
import sample_maps
import pickle
import hashlib

import perf_recorder as _pr
pr = _pr.get_perf_recorder()

DBG = True
DBG = False

_acc_debug = "ACCUMULATED_DURATION_DBG" in os.environ
if not _acc_debug:
    print("WARN: Accumulated duration debug is NOT enabled as ACCUMULATED_DURATION_DBG envvar is missing\n"*20)
else:
    print("INFO: Accumulated duration debug is enabled as ACCUMULATED_DURATION_DBG envvar is present")

_def_closest_stars_to_check = 3
_def_max_dist_diff = 50
_def_max_size_diff = 50
_def_stop_after_miss_stars = 10
_def_plot_results = 5
_def_max_angle_dist_diff = 50

STAR_X = 0
STAR_Y = 1
STAR_SZ = 2

import logging

angle_dist_K = 100 * (1/360) * 2 * math.pi

pending_improvements = '''
NEXT STEPS:

PENDING
----------------------
2. Implement pickle save and restor for star map angles and distances

3. Count unmatched stars on the reference map. Still not sure how to identify which ones to count. Try to build a poligon with 
   Lines encompasing all matched stars and test those inside? Figure out how to add it into the score.

4. Check how are we handling the score for unmatched stars


DONE
----------------------
-1 Change the way to do size calibration not to rely on star size but distance. Should be way more precise!

0. Check why, when the same map is evaluated out of different start stars, different scale factors come up although angle and 
   score is very similar.
   Once solved, re-enable optimization after # Check if this combination has been evaluated already

1. Receive an input parameter of the expected number of tiles on the map, corresponding to the number of tiles on the puzzle
   This size will be used to calculate the max distance (with a good marging) for which to calculate distances from a star
   Comparison will be made for x,x and y,y coordinates, no need to calculate the actual distance to know if we..., you get it!

2. For the angle error, convert it to a distance as the portion of a circle with the given angle or radius r = star_distance
   This will tolerate big angle errors on close stars while properly penalizing big angle differences on separated stars.
   weight the error agains the angle distance or whatever comparison we are doing for distance errors. Error percentage could go
   above 100% but that's ok since we want large errors to be properly penalized



'''

def generate_md5_hash(input_string):
    """
    Generates the MD5 hash of a given string.

    Args:
        input_string (str): The string to be hashed.

    Returns:
        str: The 32-character hexadecimal MD5 hash.
    """
    # MD5 requires byte-like objects, so encode the string
    encoded_string = input_string.encode('utf-8')

    # Create an MD5 hash object
    md5_hash = hashlib.md5()

    # Update the hash object with the encoded string
    md5_hash.update(encoded_string)

    # Get the hexadecimal representation of the hash
    hex_digest = md5_hash.hexdigest()

    return hex_digest

_pickle_db = {}
def pickle_factory(fname):
    global _pickle_db
    fname = os.path.realpath(fname)
    if fname not in _pickle_db:
        with open(fname, "rb") as fh:
            _pickle_db[fname] = pickle.load(fh)
    return _pickle_db[fname]
    

def init_logger(name: str, log_file: str, file_level=logging.INFO, console_level=logging.DEBUG):
    global _log
    """
    Initialize a logger with both console and file handlers.
    
    Args:
        name (str): Logger name.
        log_file (str): Path to the log file.
        file_level (int): Logging level for the file handler.
        console_level (int): Logging level for the console handler.
        
    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Capture all, handlers filter levels

    # Avoid duplicate handlers if function called multiple times
    if not logger.handlers:
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

        # File handler
        fh = logging.FileHandler(log_file)
        fh.setLevel(file_level)
        fh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

        # Add handlers
        logger.addHandler(ch)
        logger.addHandler(fh)

    _log = logger
    return logger

def _adj_angle(a):
    if a >= 360:
        return a % 360
    while a < 0:
        a += 360
    return a

def angle_abs_diff(a, b):
    d = _adj_angle(abs(a - b))
    if d > 180:
        d = 360 - d
    return d

_next_score_ID = 0
class Score:
    def __init__(self, templ_refA_star, 
                       templ_refB_star,
                       tile_refA_star,
                       tile_refB_star,
                       size_adj_factor,
                       adj_angle):
        global _next_score_ID
        self.templ_refA_star = templ_refA_star
        self.templ_refB_star = templ_refB_star
        self.tile_refA_star = tile_refA_star
        self.tile_refB_star = tile_refB_star
        self.size_adj_factor = size_adj_factor
        self.adj_angle = adj_angle
        self._tile_star_scores = {}
        self._tile_star_matches = {}
        self._mappings = None
        self.ranking = None
        self.score = None
        self.ID = _next_score_ID
        _next_score_ID += 1
        if DBG: _log.debug(f"New score created: ID: {self.ID}, templ_refA_star={templ_refA_star}, templ_refB_star={templ_refB_star}, tile_refA_star={tile_refA_star}, tile_refB_star={tile_refB_star}")
    
    def set_ranking(self, ranking):
        self.ranking = ranking

    def match_candidate_stars(self, ref_A, ref_B, tile_A, tile_B):
        #match = tile_A in self._mappings and tile_B in self._mappings and self._mappings[tile_A] == ref_A and self._mappings[tile_B] == ref_B
        
        # only want to match if the stars in question were directly matched.
        # Don't care if these were loosy matched on a match with different match stars because that may be a low score match with bad ref start candidates
        match = (ref_A == self.templ_refA_star and ref_B == self.templ_refB_star and tile_A == self.tile_refA_star and tile_B == self.tile_refB_star) or \
                (ref_B == self.templ_refA_star and ref_A == self.templ_refB_star and tile_B == self.tile_refA_star and tile_A == self.tile_refB_star)
        if match:
            if DBG: _log.debug(f"Match for templ_refA_star={ref_A}, templ_refB_star={ref_B}, tile_refA_star={tile_A}, tile_refB_star={tile_B} found at score {self.ID}")
        return match
            

    def finalize(self, zero_score = False, unmatched_stars = None, unmatched_stars_weight = None):
        self._mappings = {}
        self._mappings.update(self._tile_star_matches)
        self._mappings[self.tile_refA_star] = self.templ_refA_star
        self._mappings[self.tile_refB_star] = self.templ_refB_star
        self.unmatched_stars_weight = unmatched_stars_weight
        self.unmatched_stars = unmatched_stars
        if self.unmatched_stars is None:
            self.unmatched_ratio = None
        else:
            self.unmatched_ratio = len(self._tile_star_matches) / (len(self._tile_star_matches) + self.unmatched_stars)
        if not zero_score:
            self.score = self._calculate_score()
        else:
            self.score = 0

    def register_tile_star_score(self, star, score, matched_star):
        assert self._mappings is None, "Can't add a new star after score has been finalized!"
        self._tile_star_scores[star] = score
        self._tile_star_matches[star] = matched_star

    def get_all_tile_to_templ_pairs(self):
        return dict(self._mappings)
    
    def get_matched_templ_stars(self):
        s = [s for s in self._tile_star_matches.values() if s is not None]
        return list(set(s))

    def _calculate_score(self):
        score = sum(self._tile_star_scores.values()) / (len(self._tile_star_scores))
        if self.unmatched_ratio is None:
            return score
        weight_ratio = self.unmatched_stars_weight / 100
        return (1 - weight_ratio) * score + \
               weight_ratio * score * self.unmatched_ratio

    def print_summary(self, show_hdr, score_bar_point_size = None, list_matches = False):
        if show_hdr:
            _log.info("")
            _log.info(r"ID       rank  refA_stars  refB_stars   Size    Adj     Unmatched\\")
            _log.info( "ID        ing  Ref   Tile  Ref   Tile   Factor  Angle   Strs Ratio Score")
            _log.info( "-----------------------------------------------------------------")
        if score_bar_point_size is not None:
            score_bar = int(self.score * score_bar_point_size) * "*"
        else:
            score_bar = ""

        us = f"{self.unmatched_stars}" if self.unmatched_stars is not None else "N/A"
        ur = f"{self.unmatched_ratio:<5.3}" if self.unmatched_ratio is not None else "N/A"

        _log.info(f"{self.ID:<7}  "
                  f"{self.ranking if self.ranking is not None else "N/A":<4}  "
                  f"{self.templ_refA_star:<5} "
                  f"{self.tile_refA_star:<5} "
                  f"{self.templ_refB_star:<5} "
                  f"{self.tile_refB_star:<5}  "
                  f"{self.size_adj_factor:<6.3f}  "
                  f"{self.adj_angle:<6.2f}  "
                  f"{us:3}  "
                  f"{ur:5}  "
                  f"{self.score:<7.2f}  "
                  f"{score_bar}"
                  )
        if list_matches:
            _log.info( "")
            _log.info( "    Tile Star  Match Ref  Score")
            _log.info( "  --------------------------------")
            
            for ts in range(len(self._mappings)):
                rs = self._mappings[ts]
                if rs is None:
                    rs = "N/A"
                if ts in self._tile_star_scores:
                    _log.info(f"    {ts:9}  {rs:9}  {self._tile_star_scores[ts]:.2f}")
                elif ts == self.tile_refA_star:
                    _log.info(f"    {ts:9}  {rs:9}  RefA")
                else:
                    _log.info(f"    {ts:9}  {rs:9}  RefB")

class StarMap:

    def __init__(self, stars, exp_tile_count = None, from_picture = False, stars_pickle = None, force_scan = False):
        if not from_picture:
            self._stars = stars
            self.from_pic_y_correction = None
        else:
            max_y = 0
            for x, y, s in stars:
                max_y = max(max_y, y)
            self._stars = []
            for x, y, s in stars:
                self._stars.append((x, max_y - y, s))
            self.from_pic_y_correction = max_y

        self._force_scan = force_scan
        self._star_distances = None
        self._star_angles = None
        self._max_distance = None
        self._max_size = None
        self._stars_by_distance = None
        self._exp_tile_count = exp_tile_count
        self._stars_pickle = stars_pickle
        assert self._exp_tile_count is None or \
            (type(self._exp_tile_count) in (list, tuple) and \
             len(self._exp_tile_count) == 2 and \
             type(self._exp_tile_count[0]) is int and \
             type(self._exp_tile_count[1]) is int), "exp_tile_count should be None or list/tuple of two int. Got %s"%(repr(self._exp_tile_count))
        self._build_map()

    def dump_map(self, var_name):
        map = []
        map.append("%s = ("%(var_name,))
        for i, (x, y, s) in enumerate(self._stars):
            map.append("  (%-7s, %-7s, %-7s), # Star %i"%(x, y, s, i))
        map.append(")")
        _log.info("# Map dump\n%s"%("\n".join(map)))

    def adjust_to_angle_and_size(self, adj_angle, size_adj_factor):
        score = types.SimpleNamespace()
        score.adj_angle = adj_angle
        score.size_adj_factor = size_adj_factor
        return self.adjust_to_score(score)

    def adjust_to_score(self, score):
        '''Will apply a correction for two things:
    angle, as defined by score.adj_angle
    size, as defined by score.size_adj_factor'''
        _stars = []
        angle_rad = math.radians(score.adj_angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        
        adjusted = []
        for x, y, s in self._stars:
            # Apply scaling
            x_scaled = x * score.size_adj_factor
            y_scaled = y * score.size_adj_factor
            
            # Apply rotation
            x_rot = x_scaled * cos_a - y_scaled * sin_a
            y_rot = x_scaled * sin_a + y_scaled * cos_a
            
            _stars.append((x_rot, y_rot, s*score.size_adj_factor))
        return StarMap(_stars)
    
    def _build_map(self):
        '''Calculates distances and angles between each star
        '''
        pr.record_checkpoint("StarMap.build() start")
        if self._stars_pickle is not None:
            pickle_dir = "pickle.star_maps"
            if not os.path.exists(pickle_dir):
                os.mkdir(pickle_dir)

            pickle_file = os.path.abspath(os.path.join(pickle_dir, f"star_map.{os.path.basename(self._stars_pickle)}"))

            if os.path.exists(pickle_file) and not self._force_scan:
                pr.record_checkpoint("StarMap.build(), loading pickle start")
                _log.info("Pickle file found referenced stars pickle %s"%(self._stars_pickle,))
                _log.info("  |--> Size: %.3f MiB"%(os.stat(pickle_file).st_size/(1024**2),))
                _log.info("  \\--> File: %s"%(pickle_file,))

                print("Loading pickle...", end="", flush=True)
                package = pickle_factory(pickle_file)
                #with open(pickle_file, "rb") as fh:
                #    package = pickle.load(fh)
                print("\rPickle has been loaded", end="\r", flush=True)
                self._star_distances = package.star_distances
                self._star_angles = package.star_angles
                self._stars_by_distance = package.stars_by_distance
                self._max_distance = package.max_distance
                self._max_size = package.max_size
                
                pr.record_checkpoint("StarMap.build() completed")
                return
            
            _log.info("Pickle file not found, calculating map from scratch!")
            _log.info("  \\--> %s"%(repr(pickle_file)))
        
        pr.record_checkpoint("StarMap.build(), calculating map")

        # fill empty distances list. Use lists instead of dict, may help with performance?
        _log.info("Building a map for %i stars"%(len(self._stars),))

        # if this is a template map then we'll get the expected number of x,y
        if self._exp_tile_count is not None:
            max_x = 0
            max_y = 0
            for x, y, s in self._stars:
                max_x = max(max_x, x)
                max_y = max(max_y, y)
            
            max_x_filter = (max_x / self._exp_tile_count[0]) * 1.25
            max_y_filter = (max_y / self._exp_tile_count[1]) * 1.25
            max_diag_filter = math.sqrt(max_x_filter*max_x_filter + max_y_filter*max_y_filter)

            if DBG: _log.debug( "Expected tile count was received for this map")
            if DBG: _log.debug(f"  |--> Expected X tiles: {self._exp_tile_count[0]}")
            if DBG: _log.debug(f"  |--> Expected Y tiles: {self._exp_tile_count[1]}")
            if DBG: _log.debug(f"  |--> Max X star coord: {max_x:.2f}")
            if DBG: _log.debug(f"  |--> Max Y star coord: {max_y:.2f}")
            if DBG: _log.debug(f"  |--> Limit for star distance to compare on X (tile size + margin): {max_x_filter:.2f}")
            if DBG: _log.debug(f"  |--> Limit for star distance to compare on Y (tile size + margin): {max_y_filter:.2f}")
            if DBG: _log.debug(f"  \\--> Limit for star distance to store on diagonal (tile diag size + margin): {max_diag_filter:.2f}")
        else:
            max_x_filter = None

        self._star_distances = []
        self._star_angles = []
        self._stars_by_distance = []
        self._max_distance = 0
        self._max_size = 0
        for i in range(len(self._stars)):
            self._star_distances.append([None]*len(self._stars))
            self._star_angles.append([None]*len(self._stars))
        # Calcualte distances.
        for i in range(len(self._stars)):

            if i & 0xFF == 0:
                print("  %i/%i (%.2f %%)"
                    ""%(i, 
                        len(self._stars), 
                        100*i/len(self._stars)), 
                        end="\r", flush=True)


            for j in range(i, len(self._stars)):
                # skip distance to itself
                if i == j: 
                    continue
                s_a = self._stars[i]
                s_b = self._stars[j]

                if max_x_filter is not None and \
                    ( abs(s_a[STAR_X] - s_b[STAR_X]) > max_x_filter or \
                      abs(s_a[STAR_Y] - s_b[STAR_Y]) > max_y_filter ):
                    continue

                # Distance and angle
                d = math.sqrt((s_a[STAR_X] - s_b[STAR_X])**2 + (s_a[STAR_Y] - s_b[STAR_Y])**2)

                if max_x_filter is not None and d > max_diag_filter:
                    continue

                a = math.degrees(math.atan2(s_b[STAR_Y] - s_a[STAR_Y], s_b[STAR_X] - s_a[STAR_X]))
                
                # Fill entry for both stars
                self._star_distances[i][j] = d
                self._star_distances[j][i] = d
                self._star_angles[i][j] = a
                self._star_angles[j][i] = _adj_angle(a+180)

                self._max_distance = max(self._max_distance, d)
                self._max_size = max(self._max_size, s_a[2])
                self._max_size = max(self._max_size, s_b[2])
                
                if DBG: _log.debug(f" Star A @ idx {i}: {s_a}, star B @ idx {j}: {s_b}. Distance {d}. Angle A to B: {self._star_angles[i][j]}. Angle B to A: {self._star_angles[j][i]}")
        # Make a list of sorted stars by distance
        for i in range(len(self._stars)):
            dists = []
            for j in range(len(self._stars)):
                if i == j or self._star_distances[i][j] is None:
                    continue
                # Dist, index
                dists.append((self._star_distances[i][j], j))
            # Sort by distance
            dists = sorted(dists, key=lambda x: x[0])
            self._stars_by_distance.append([d[1] for d in dists])
            if DBG: _log.debug(f" Star @ idx {i}'s closest stars (cropped to 10 stars): %s"%(", ".join("%i"%i for i in self._stars_by_distance[i][:10])))

        if self._stars_pickle is not None:
            package = types.SimpleNamespace()
            package.star_distances = self._star_distances
            package.star_angles = self._star_angles
            package.stars_by_distance = self._stars_by_distance
            package.max_distance = self._max_distance
            package.max_size = self._max_size

            _log.info("Saving map to pickle: %s"%(pickle_file,))

            pr.record_checkpoint("StarMap.build(), saving pickle")
            with open(pickle_file, "wb") as fh:
                pickle.dump(package, fh)
        _log.info("Map build completed")
        pr.record_checkpoint("StarMap.build() completed")

    def match_tile(self, tile,
                   max_size_diff = _def_max_size_diff,
                   max_dist_diff = _def_max_dist_diff,
                   max_angle_dist_diff = _def_max_angle_dist_diff,
                   closest_stars_to_check = _def_closest_stars_to_check,
                   stop_after_miss_stars = _def_stop_after_miss_stars,
                   show_result_details = _def_plot_results,
                   size_diff_score_factor = 0.5,
                   dist_diff_score_factor = 1.0,
                   angle_dist_score_factor = 1.0,
                   exp_scale_factor = None,
                   angle_rotation_ranges = None,
                   unmatched_stars_weight = False,
                   max_listed_results = 25,
                          ):
        _log.info("Matching stars...")
        _log.debug("  |--> max_size_diff = %s"%(repr(max_size_diff),))
        _log.debug("  |--> max_dist_diff = %s"%(repr(max_dist_diff),))
        _log.debug("  |--> max_angle_dist_diff = %s"%(repr(max_angle_dist_diff),))
        _log.debug("  |--> closest_stars_to_check = %s"%(repr(closest_stars_to_check),))
        _log.debug("  |--> stop_after_miss_stars = %s"%(repr(stop_after_miss_stars),))
        _log.debug("  |--> show_result_details = %s"%(repr(show_result_details),))
        _log.debug("  |--> size_diff_score_factor = %s"%(repr(size_diff_score_factor),))
        _log.debug("  |--> dist_diff_score_factor = %s"%(repr(dist_diff_score_factor),))
        _log.debug("  |--> angle_dist_score_factor = %s"%(repr(angle_dist_score_factor),))
        _log.debug("  |--> exp_scale_factor = %s"%(repr(exp_scale_factor),))
        _log.debug("  |--> angle_rotation_ranges = %s"%(repr(angle_rotation_ranges),))
        _log.debug("  |--> unmatched_stars_weight = %s"%(repr(unmatched_stars_weight),))
        _log.debug("  \\--> max_listed_results = %s"%(repr(max_listed_results),))

        next_checkpoint = 1

        # This algoritm will test each star on the reference map against each start on the tile map
        # All scores ever
        scores = []
        # Scores on which a ref star shows up. Should make search for scores already tested way way faster!
        templ_star_scores = {}
        best_score = 0
        nxt_update = 0
        for templ_refA_star in range(len(self._stars)):
            progress = 100*templ_refA_star / len(self._stars)
            if progress > next_checkpoint:
                pr.record_checkpoint("Match at %.2f%%"%(progress,))
                next_checkpoint = int(progress) + 1
            _t = time.time()
            if _t > nxt_update:
                print("%.3f %% - Best score: %.2f out of %i checks"%(progress, best_score, len(scores)), end="\r", flush=True)
                nxt_update = _t + 0.5

            for tile_refA_star in range(len(tile._stars)):
                
                if DBG: _log.debug(f"Comparing refA stars. From ref map: {templ_refA_star}, from tile map: {tile_refA_star}")
                
                templ_refB_stars = self._stars_by_distance[templ_refA_star][:closest_stars_to_check]
                tile_refB_stars = tile._stars_by_distance[tile_refA_star][:closest_stars_to_check]
                if DBG: _log.debug("  |--> Templ refB candidates: %s"%(repr(templ_refB_stars),))
                if DBG: _log.debug("  \\--> Tile refB candidates: %s"%(repr(tile_refB_stars),))
                for templ_refB_star in templ_refB_stars:
                    for tile_refB_star in tile_refB_stars:
                        # Check if this combination has been evaluated already
                        # Re-enable once results make sense! Seeing different scaling factors when the same tile is matched different times out of different start stars
                        #if any([score.match_candidate_stars(templ_refA_star, templ_refB_star, tile_refA_star, tile_refB_star) for score in scores]):
                        #    if DBG: _log.debug(f"Combination already verified: templ_refA_star={templ_refA_star}, templ_refB_star={templ_refB_star}, tile_refA_star={tile_refA_star}, tile_refB_star={tile_refB_star}")
                        #    continue

                        if _acc_debug:
                            t0 = time.time()

                        # Calculate size/dist adjustment factor based on the refA-refB distances
                        templ_map_refAB_dist = self._star_distances[templ_refA_star][templ_refB_star]
                        tile_map_refAB_dist = tile._star_distances[tile_refA_star][tile_refB_star]

                        if _acc_debug:
                            t1 = time.time()
                            pr.record_segment_accumulated_duration("match_tile.star_distances_access", t1 - t0)

                        tile_scale_factor = templ_map_refAB_dist / tile_map_refAB_dist

                        if exp_scale_factor is not None and \
                            ( tile_scale_factor < exp_scale_factor[0] or \
                              tile_scale_factor > exp_scale_factor[1] ):
                            # should we save an score?
                            continue

                        # Check if this combination has been evaluated already
                        # Re-enable once results make sense! Seeing different scaling factors when the same tile is matched different times out of different start stars
                        #if any([score.match_candidate_stars(templ_refA_star, templ_refB_star, tile_refA_star, tile_refB_star) for score in scores]):

                        if templ_refA_star in templ_star_scores and \
                            any([score.match_candidate_stars(templ_refA_star, templ_refB_star, tile_refA_star, tile_refB_star) for score in templ_star_scores[templ_refA_star]]):
                            if DBG: _log.debug(f"Combination already verified: templ_refA_star={templ_refA_star}, templ_refB_star={templ_refB_star}, tile_refA_star={tile_refA_star}, tile_refB_star={tile_refB_star}")
                            if _acc_debug:
                                t2 = time.time()
                                pr.record_segment_accumulated_duration("match_tile.match_candidate_stars->match", t2 - t1)
                            continue
                        if _acc_debug:
                            t2 = time.time()
                            pr.record_segment_accumulated_duration("match_tile.match_candidate_stars->no match", t2 - t1)
                        
                        tile_max_star_dist_adj = tile._max_distance * tile_scale_factor
                        tile_max_star_size_adj = tile._max_size * tile_scale_factor

                        # Verify both star sizes are on range
                        # And calculate some other values with the purpose of logging
                        templ_refA_size = self._stars[templ_refA_star][STAR_SZ]
                        tile_refA_adj_size = tile._stars[tile_refA_star][STAR_SZ] * tile_scale_factor
                        refA_size_error = (100 * abs(tile_refA_adj_size - templ_refA_size) / templ_refA_size)
                        
                        templ_refB_size = self._stars[templ_refB_star][STAR_SZ]
                        tile_refB_adj_size = tile._stars[tile_refB_star][STAR_SZ] * tile_scale_factor
                        refB_size_error = (100 * abs(tile_refB_adj_size - templ_refB_size) / templ_refB_size)

                        adj_angle = _adj_angle(self._star_angles[templ_refA_star][templ_refB_star] - tile._star_angles[tile_refA_star][tile_refB_star])
                        if DBG:
                            _log.debug("Angle from templ_refA_star to templ_refB_star: %.2f"%(self._star_angles[templ_refA_star][templ_refB_star],))
                            _log.debug("Angle from tile_refA_star to tile_refB_star: %.2f"  %(tile._star_angles[tile_refA_star][tile_refB_star],))
                            _log.debug("Un-adjusted angle: : %.2f"  %(self._star_angles[templ_refA_star][templ_refB_star] - tile._star_angles[tile_refA_star][tile_refB_star],))

                        if angle_rotation_ranges is not None and \
                            not any([adj_angle > r[0] and adj_angle < r[1] for r in angle_rotation_ranges]):
                            if DBG: _log.debug("Angles out of range, skipping!")
                            continue
                        
                        if _acc_debug:
                            t3 = time.time()
                            pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_0", t3 - t2)

                        score = Score(templ_refA_star, 
                                      templ_refB_star, 
                                      tile_refA_star, 
                                      tile_refB_star,
                                      tile_scale_factor,
                                      adj_angle)
                        scores.append(score)
                        
                        if templ_refA_star not in templ_star_scores:
                            templ_star_scores[templ_refA_star] = []
                        templ_star_scores[templ_refA_star].append(score)

                        if templ_refB_star not in templ_star_scores:
                            templ_star_scores[templ_refB_star] = []
                        templ_star_scores[templ_refB_star].append(score)

                        
                        if DBG: _log.debug(f"    Comparing to refB stars. templ_refB_star: {templ_refB_star}, tile_refB_star: {tile_refB_star}")
                        if DBG: _log.debug(f"      |--> templ_refA_star: {templ_refA_star}")
                        if DBG: _log.debug(f"      |--> tile_refA_star: {tile_refA_star}")
                        if DBG: _log.debug(f"      |--> tile_scale_factor: {tile_scale_factor:.3f}")
                        if DBG: _log.debug(f"      |--> Size error refA: {refA_size_error}%")
                        if DBG: _log.debug(f"      |--> Size error refB: {refB_size_error}%")
                        if DBG: _log.debug( "      |--> Score ID: %i"%(score.ID,))
                        if DBG: _log.debug( "      |--> Adjustment angle: %.3f deg"%(adj_angle,))
                        
                        if refA_size_error > max_size_diff or \
                           refB_size_error > max_size_diff:
                            if DBG: _log.debug(f"      \\--> One or two refX size errors are above max. Skipping this pair!")
                            score.finalize(zero_score = True)
                            continue

                        if DBG: _log.debug(f"      \\--> RefA/B size errors under tolerance, continuing...")

                        #tile_max_star_dist_adj = tile._max_distance * tile_scale_factor
                        #tile_max_star_size_adj = tile._max_size * tile_scale_factor
                        
                        # if DBG: _log.debug("    Some additional parameters:")
                        # if DBG: _log.debug("      |--> max star size of stars on tile (adjusted): %.4f"%(tile_max_star_size_adj,))
                        # if DBG: _log.debug("      \\--> max star distance of stars on tile (adjusted): %.4f"%(tile_max_star_dist_adj,))
                        # if DBG: _log.debug("    Comparing all remaining tile stars to match expected angles and distances on ref map stars")

                        # Matching stars should met these conditions in order to be considered a match, as compared to ref_A star:
                        # 
                        # > A distance error no larger than max_dist_diff % of the max distance between any star on the tile
                        # > a size error no larger than max_size_diff % of the max size found on the tile (adjusted with the scale factor)
                        # > an Angle distance error no larger than _max_angle_dist %
                        zero_score_count = 0
                        for tile_test_star in range(len(tile._stars)):
                            # Skip the two reference stars
                            if tile_test_star in (tile_refA_star, tile_refB_star):
                                continue

                            if _acc_debug:
                                t4 = time.time()

                            # get adjusted distance and angle to refA and then see if a matching star exists on ref map
                            tile_test_star_adj_dist = tile._star_distances[tile_refA_star][tile_test_star] * tile_scale_factor
                            tile_test_star_adj_angle = _adj_angle(tile._star_angles[tile_refA_star][tile_test_star] + adj_angle)
                            tile_test_star_adj_size = tile._stars[tile_test_star][STAR_SZ] * tile_scale_factor

                            if _acc_debug:
                                t5 = time.time()
                                pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_1", t5 - t4)

                            # Will test ref map stars by distance from refA star
                            # Don't expect there to be too many stars, tiles should have a handful stars usually
                            # and the ref map will have thousands of stars
                            # So, does not even make sense to try a binary search or something like that
                            # will test in order by distance
                            templ_test_stars_scores = {}
                            
                            if DBG:
                                _log.debug(f"        Finding a match for tile star {tile_test_star}")
                                _log.debug(f"          |--> Tile scale factor: %.4f"%(tile_scale_factor,))
                                _log.debug(f"          |--> adjusted distance to tile A star: {tile_test_star_adj_dist}")
                                _log.debug(f"          |--> adjusted size: {tile_test_star_adj_size}")
                                _log.debug(f"          |--> adjusted angle to tile A star: {tile_test_star_adj_angle}")
                                _log.debug(f"          |--> candidate stars to test (count): {len(self._stars_by_distance[templ_refA_star])}")

                            for templ_test_star in self._stars_by_distance[templ_refA_star]:
                                if DBG: _log.debug(f"          |   |--> testing against ref star: {templ_test_star}")
                                # Don't include temp ref B star on the comparison, it is already matched
                                if templ_test_star == templ_refB_star:
                                    if DBG: _log.debug(f"          |   |--> skipping ref B star")
                                    continue
                                templ_test_star_dist = self._star_distances[templ_refA_star][templ_test_star]
                                # I guess some random maps may put stars very very close to each other?
                                if templ_test_star_dist < 0.1:
                                    if DBG: _log.debug(f"          |   |--> skipping too-close of a star with distance {templ_test_star_dist}")
                                    continue

                                if _acc_debug:
                                    t5a = time.time()
                            
                                templ_test_star_size = self._stars[templ_test_star][STAR_SZ]
                                templ_test_star_angle = self._star_angles[templ_refA_star][templ_test_star]

                                #if _acc_debug:
                                #    t5b = time.time()
                                #    pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2.A", t5b - t5a)

                                templ_test_stars_scores[templ_test_star] = 100

                                if _acc_debug:
                                    t5b = time.time()
                                    pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2.A_1", t5b - t5a)

                                #if DBG: _log.debug(f"          | Comparing against ref star {templ_test_star}")

                                # Distance error
                                dist_err = abs(templ_test_star_dist - tile_test_star_adj_dist) * 100 / tile_max_star_dist_adj
                                if DBG: _log.debug(f"          |   |--> Distance error: {dist_err:.2f}%%")
                                
                                if _acc_debug:
                                    t5c = time.time()
                                    pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2.B", t5c - t5b)

                                if dist_err > max_dist_diff:
                                    if DBG: _log.debug(f"          |   \\--> Distance error above limit, score = 0")
                                    templ_test_stars_scores[templ_test_star] = 0
                                    # optimization. We are on a star with a distance larger than tolerated, abort
                                    if templ_test_star_dist > tile_test_star_adj_dist:
                                        break
                                    if _acc_debug:
                                        t5d = time.time()
                                        pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2.C_2", t5d - t5c)
                                    continue
                                templ_test_stars_scores[templ_test_star] -= dist_err
                                
                                # Size error
                                size_err = abs(templ_test_star_size - tile_test_star_adj_size) * 100 / tile_max_star_size_adj 
                                if DBG: _log.debug(f"          |   |--> Size error: {size_err:.2f}%%")
                                if size_err > max_size_diff:
                                    if DBG: _log.debug(f"          |   \\--> Size error above limit, score = 0")
                                    templ_test_stars_scores[templ_test_star] = 0
                                    if _acc_debug:
                                        t5d = time.time()
                                        pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2.C_0", t5d - t5c)

                                    continue

                                if _acc_debug:
                                    t5d = time.time()
                                    pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2.C_1", t5d - t5c)

                                templ_test_stars_scores[templ_test_star] -= size_err

                                angle_err = angle_abs_diff(templ_test_star_angle, tile_test_star_adj_angle)
                                angle_dist_err = angle_err * templ_test_star_dist * angle_dist_K / tile_max_star_dist_adj
                                if DBG: _log.debug(f"          |   |--> Angle distance error: {angle_dist_err:.2f}%%")
                                if DBG: _log.debug(f"          |   |     |--> angle_err: {angle_err:.2f}%%")
                                if DBG: _log.debug(f"          |   |     \\--> templ_test_star_dist: {templ_test_star_dist:.2f}%%")
                                if angle_dist_err > max_angle_dist_diff:
                                    if DBG: _log.debug(f"          |   \\--> Angle distance error above limit, score = 0")
                                    templ_test_stars_scores[templ_test_star] = 0
                                    if _acc_debug:
                                        t5e = time.time()
                                        pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2.D_0", t5e - t5d)
                                    continue
                                templ_test_stars_scores[templ_test_star] -= angle_dist_err
                                if DBG: _log.debug(f"          |   \\--> Final star score: {templ_test_stars_scores[templ_test_star]:.2f}")

                                if _acc_debug:
                                    t5e = time.time()
                                    pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2.D_1", t5e - t5d)
                                
                            if _acc_debug:
                                t6 = time.time()
                                pr.record_segment_accumulated_duration("match_tile.score_calculation.phase_2", t6 - t5)

                            # Register the highest score
                            tile_test_star_score = 0
                            tile_test_star_matching_star = None
                            for st, sc in templ_test_stars_scores.items():
                                if sc > tile_test_star_score:
                                    tile_test_star_score = sc
                                    tile_test_star_matching_star = st
                            if DBG: _log.debug(f"          |--> tile test star score: {tile_test_star_score:.2f}")
                            if DBG: _log.debug(f"          \\--> tile test star matched ref star: {tile_test_star_matching_star}")
                            score.register_tile_star_score(tile_test_star, tile_test_star_score, tile_test_star_matching_star)
                            if tile_test_star_score == 0:
                                zero_score_count += 1
                                if zero_score_count >= stop_after_miss_stars:
                                    break
                        
                        zero_score = zero_score_count >= stop_after_miss_stars
                        unmatched_stars = None

                        if (not zero_score):
                            # now, let's check how many un-matched stars are there on the templ side inside the smallest box which contains all the matched stars
                            matched_templ_stars = score.get_matched_templ_stars()
                            if len(matched_templ_stars) > 0:
                                if DBG:
                                    _log.debug("Counting templ stars not matched inside the matched box")
                                    _log.debug("matched stars to analyze: %s"%(matched_templ_stars,))
                                min_x, max_x, min_y, max_y = self.get_min_size_box(matched_templ_stars)
                                box_diag_size = math.sqrt((max_x - min_x)**2 + (max_y - min_y)**2)
                                if DBG:
                                    _log.debug("Box diag size: %s"%(box_diag_size,))
                                unmatched_stars = 0
                                for check_star in self._stars_by_distance[matched_templ_stars[0]]:
                                    if check_star in matched_templ_stars:
                                        if DBG: 
                                            _log.debug("Skipping matched star: %s"%(check_star,))
                                        continue
                                    if self._star_distances[matched_templ_stars[0]][check_star] > box_diag_size:
                                        if DBG: 
                                            _log.debug("Stopping check at start %i with distance %s"%(check_star, self._star_distances[matched_templ_stars[0]][check_star]))
                                        break
                                    if self._stars[check_star][STAR_X] >= min_x and \
                                        self._stars[check_star][STAR_X] <= max_x and \
                                        self._stars[check_star][STAR_Y] >= min_y and \
                                        self._stars[check_star][STAR_Y] <= max_y:
                                        unmatched_stars += 1
                                        if DBG:
                                            _log.debug("Un-matched star inside the box: %s"%(check_star,))
                                unmatched_ratio = len(matched_templ_stars) / (unmatched_stars + len(matched_templ_stars))
                                if DBG:
                                    _log.debug("Unmatched stars in box: %s"%(unmatched_stars,))
                                    _log.debug("Unmatched stars ratio: %s"%(unmatched_ratio,))
                        
                        score.finalize(zero_score = zero_score, unmatched_stars = unmatched_stars, unmatched_stars_weight = unmatched_stars_weight)
                        best_score = max(best_score, score.score)
                        if DBG: _log.debug(f"    Final score: {score.score}")
        # Sort scores by score
        scores = sorted(scores, key=lambda x: x.score, reverse=True)
        
        max_score = max([score.score for score in scores])
        if max_score == 0:
            _log.error("No good matches found! :(")
            return None
        
        score_bar_point_size = 80 / max_score
        for idx, score in enumerate(scores):
            #if score.score < 70:
            #    _log.warning("Not showing results for %i scores below 70"%(len(scores) - idx))
            #    break
            if max_listed_results is not None and idx >= max_listed_results:
                _log.warning("Not showing results for %i scores, limited to first %i results"%(len(scores) - idx, max_listed_results))
                break
            score.set_ranking(idx)
            score.print_summary(show_hdr = idx <= show_result_details, score_bar_point_size = score_bar_point_size, list_matches = idx < show_result_details)
            
        
        return scores

    def get_min_size_box(self, stars):
        assert len(stars) > 0, "got no stars!"
        min_x = max_x = min_y = max_y = None
        for star in stars:
            min_x = self._stars[star][STAR_X] if min_x is None else min(min_x, self._stars[star][STAR_X])
            max_x = self._stars[star][STAR_X] if max_x is None else max(max_x, self._stars[star][STAR_X])
            min_y = self._stars[star][STAR_Y] if min_y is None else min(min_y, self._stars[star][STAR_Y])
            max_y = self._stars[star][STAR_Y] if max_y is None else max(max_y, self._stars[star][STAR_Y])
        if DBG:
            _log.debug("Min box size for stars")
            _log.debug("  |--> stars: %s"%(repr(stars),))
            _log.debug("  |--> X: %s - %i"%(min_x, max_x,))
            _log.debug("  \\--> Y: %s - %i"%(min_y, max_y,))
        return min_x, max_x, min_y, max_y

def plot_map(map, title):
    import matplotlib.pyplot as plt

    # Separate into x, y, size lists
    x = [d[0] for d in map._stars]
    y = [d[1] for d in map._stars]
    sizes = [100*d[2]/map._max_size for d in map._stars]

    plt.figure(figsize=(6, 6))
    plt.scatter(x, y, s=sizes, c="yellow", alpha=0.6, edgecolors="black")

    # Add index numbers to each dot
    for i, (xi, yi) in enumerate(zip(x, y)):
        plt.text(xi, yi, str(i), fontsize=9,
                ha="center", va="center", color="black", weight="bold")

    plt.xlabel("X-axis")
    plt.ylabel("Y-axis")
    plt.title(title)
    plt.grid(True)
    plt.show(block = False)

def arg_x_y_count(txt):
    s = txt.split(",")
    assert len(s) == 2, "x-y count expects two comma-separated items, got %s"%(repr(txt),)
    try:
        s[0] = int(s[0])
        s[1] = int(s[1])
    except ValueError as ex:
        raise argparse.ArgumentError(message = "Can't convert X,Y count into integer: %s"%(repr(txt),))
    return s[0],s[1]

def arg_rot_90deg_range(txt):
    try:
        limit = float(txt)
        assert limit > 0 and limit < 45, "90 degress tolerance must be larger than 0 degrees and less than 45 (which would allow any angle)"
        # Add two ranges around 360, otherwise it is more difficult to compare
        ranges = ((-0.001, limit),
                  (360 - limit, 360.001),
                  (90 - limit, 90 + limit),
                  (180 - limit, 180 + limit),
                  (270 - limit, 270 + limit))
        return ranges
    except Exception as ex:
        print(ex)
        raise

def arg_scale_factor(txt):
    s = txt.split(",")
    assert len(s) == 2, "scale factor expects two comma-separated items, got %s"%(repr(txt),)
    try:
        s[0] = float(s[0])
        s[1] = float(s[1])
    except ValueError as ex:
        raise argparse.ArgumentError(message = "Can't convert X,Y count into integer: %s"%(repr(txt),))
    assert s[0] < s[1], "Scale factor should be two float numbers where the first one is smaller. Got %s"%(repr(txt),)
    return s[0],s[1]

def main():
    global _log

    parser = argparse.ArgumentParser(description="Mock mode checker options")
    parser.add_argument("-L", "--logfile",          dest="logfile",                 default=None, help="Path to log file")
    parser.add_argument("--ref_map",                dest="ref_map",                 default=None, help="ID for the map to use as reference")
    parser.add_argument("--tile_map",               dest="tile_map",                default=None, help="ID for the map to use as tile")
    parser.add_argument("--max_size_diff",          dest="max_size_diff",           default=_def_max_size_diff,           type=float,    help="Max tolerated star size difference, in percentage. Default: %(default)s%%")
    parser.add_argument("--max_dist_diff",          dest="max_dist_diff",           default=_def_max_dist_diff,           type=float,    help="Max tolerated star distance difference as a percentage. Default: %(default)s%%")
    parser.add_argument("--max_angle_dist_diff",    dest="max_angle_dist_diff",     default=_def_max_angle_dist_diff,     type=float,    help="Max tolerated angle-distance error, as a percentage. Default: %(default)s%%")
    parser.add_argument("--exp_ref_tile_count",     dest="exp_ref_tile_count",      default=None,                         type=arg_x_y_count,    help="Expected count of X and Y tiles/puzzle pieces on the template/reference map. Default: %(default)s%%")
    parser.add_argument("--closest_stars_to_check", dest="closest_stars_to_check",  default=_def_closest_stars_to_check,  type=float,    help="Number of stars closest to every tested reference pair of stars on tile and ref map to test matches for. Default: %(default)s")
    parser.add_argument("--stop_after_miss_stars",  dest="stop_after_miss_stars",   default=_def_stop_after_miss_stars,   type=float,    help="Stop after these many stars from the tile are not found on the reference map. Default: %(default)s")
    parser.add_argument("--plot_results",           dest="plot_results",            default=_def_plot_results,            type=int,      help="From the best results plot these many. Default: %(default)s")
    args =  parser.parse_args()

    if args.ref_map is None or args.ref_map not in sample_maps.test_maps:
        raise Exception("Pls provide a valid ref_map value. Got %s. Valid: %s"%(args.ref_map, " ".join(sample_maps.test_maps.keys()),))
    if args.tile_map is None or args.tile_map not in sample_maps.test_maps:
        raise Exception("Pls provide a valid tile_map value. Got %s. Valid: %s"%(args.tile_map, " ".join(sample_maps.test_maps.keys()),))
    if args.logfile is None:
        logs_dir =os.path.join(os.getcwd(), "LOGS")
        if not os.path.exists(logs_dir):
            os.mkdir(logs_dir)
        args.logfile = os.path.join(logs_dir, os.path.splitext(os.path.basename(sys.argv[0]))[0] + time.strftime("%y%m%d_%H%M%S") + "__" + args.ref_map + "__vs__" + args.tile_map + ".log")
    _log = init_logger(name = sys.argv[0], 
                    log_file = args.logfile,
                    file_level=logging.DEBUG, 
                    console_level=logging.INFO)
    _pr._log = _log
    _log.info("Logger name: %s"%(args.logfile,))

    _log.warning(pending_improvements)

    # Make a random map?
    # stars = sample_maps.make_random_map(2500,
    #                         max_x = 2000,
    #                         max_y = 2000)
    # map = StarMap(stars)
    # map = StarMap(sample_maps.test_maps[args.ref_map], exp_tile_count = args.exp_ref_tile_count)
    # plot_map(map, "ref A map")
    # return

    # Adjust a tile map for scale and angle?
    #tile_B_1 = StarMap(sample_maps._tile_map_C_0).adjust_to_angle_and_size(adj_angle = -175, size_adj_factor = 4.3)._stars
    #import pprint
    #pprint.pprint(tile_B_1)
    #return

    t0 = time.time()
    ref_map = StarMap(sample_maps.test_maps[args.ref_map], exp_tile_count = args.exp_ref_tile_count)
    t1 = time.time()
    tile_map = StarMap(sample_maps.test_maps[args.tile_map])
    t2 = time.time()
    scores = ref_map.match_tile(tile_map,
                                 max_size_diff = args.max_size_diff,
                                 max_dist_diff = args.max_dist_diff,
                                 max_angle_dist_diff = args.max_angle_dist_diff,
                                 closest_stars_to_check = args.closest_stars_to_check,
                                 stop_after_miss_stars = args.stop_after_miss_stars,
                                 show_result_details = args.plot_results,
                                )
    t3 = time.time()
    
    plot_map(ref_map, "Reference Map")
    plot_map(tile_map, "Tile Map")

    # s = types.SimpleNamespace()
    # s.size_adj_factor = 1
    # s.adj_angle = 270   
    # tile_rotated = tile_map.adjust_to_score(s)
    # plot_map(tile_rotated, "Tile Map rotated")

    for idx, score in enumerate(scores[:args.plot_results]):
        if score.score < 75:
            continue
        adj_map = tile_map.adjust_to_score(score)
        plot_map(adj_map, "Adjusted solution %i. score: %.3f, size: %.3f, angle: %.2f"%(idx, score.score, score.size_adj_factor, score.adj_angle))
    
    _log.info("Reference map build time: %.3f secs"%(t1-t0))
    _log.info("     Tile map build time: %.3f secs"%(t2-t1))
    _log.info("            Map Matching: %.3f secs"%(t3-t2))

if __name__ == "__main__":
    main()
    input("Hit ENTER to exit...")
    


