import argparse
import math
import sys
import os
import time
import types

_def_closest_stars_to_check = 3
_def_max_dist_diff = 50
_def_max_size_diff = 50
_def_stop_after_miss_stars = 5
_def_max_angle_diff = None

STAR_X = 0
STAR_Y = 1
STAR_SZ = 2

import logging

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

class Score:
    def __init__(self, ref_refA_star, 
                       ref_refB_star,
                       tile_refA_star,
                       tile_refB_star,
                       size_adj_factor,
                       adj_angle):
        self.ref_refA_star = ref_refA_star
        self.ref_refB_star = ref_refB_star
        self.tile_refA_star = tile_refA_star
        self.tile_refB_star = tile_refB_star
        self.size_adj_factor = size_adj_factor
        self.adj_angle = adj_angle
        self._tile_star_scores = {}
        self._tile_star_matches = {}
    
    def register_tile_star_score(self, star, score, matched_star):
        self._tile_star_scores[star] = score
        self._tile_star_matches[star] = matched_star

    def get_score(self):
        return sum(self._tile_star_scores.values())

    def print_summary(self, show_hdr, score_bar_point_size = None, list_matches = False):
        if show_hdr:
            _log.info(r"refA_stars refB_stars   Size    Adj")
            _log.info( "Ref  Tile  Ref  Tile   Factor  Angle   Score")
        score = self.get_score()
        if score_bar_point_size is not None:
            score_bar = int(score * score_bar_point_size) * "*"
        else:
            score_bar = ""


        _log.info(f"{self.ref_refA_star:4}  "
                  f"{self.tile_refA_star:4}  "
                  f"{self.ref_refB_star:4}  "
                  f"{self.tile_refB_star:4}  "
                  f"{self.size_adj_factor:6.3f}  "
                  f"{self.adj_angle:6.1f}  "
                  f"{score:7.2f}  "
                  f"{score_bar}"
                  )
        if list_matches:
            _log.info( "    Tile Star  Match Ref  Score")
            _log.info(f"    {self.tile_refA_star:9}  {self.ref_refA_star:9}  RefA")
            _log.info(f"    {self.tile_refB_star:9}  {self.ref_refB_star:9}  RefB")
            for ts, rs in self._tile_star_matches.items():
                _log.info(f"    {ts:9}  {rs:9}  {self._tile_star_scores[ts]:.2f}")

class StarMap:
    def __init__(self, stars):
        self._stars = stars
        self._star_distances = None
        self._star_angles = None
        self._max_distance = None
        self._max_size = None
        self._stars_by_distance = None
        self._build_map()

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
        # fill empty distances list. Use lists instead of dict, may help with performance?
        _log.info("Building a map for %i stars"%(len(self._stars),))
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
            for j in range(i, len(self._stars)):
                # skip distance to itself
                if i == j: 
                    continue
                s_a = self._stars[i]
                s_b = self._stars[j]

                # Distance and angle
                d = math.sqrt((s_a[STAR_X] - s_b[STAR_X])**2 + (s_a[STAR_Y] - s_b[STAR_Y])**2)
                a = math.degrees(math.atan2(s_b[STAR_Y] - s_a[STAR_Y], s_b[STAR_X] - s_a[STAR_X]))
                
                # Fill entry for both stars
                self._star_distances[i][j] = d
                self._star_distances[j][i] = d
                self._star_angles[i][j] = a
                self._star_angles[j][i] = _adj_angle(a+180)

                self._max_distance = max(self._max_distance, d)
                self._max_size = max(self._max_size, s_a[2])
                self._max_size = max(self._max_size, s_b[2])
                
                _log.debug(f" Star A @ idx {i}: {s_a}, star B @ idx {j}: {s_b}. Distance {d}. Angle A to B: {self._star_angles[i][j]}. Angle B to A: {self._star_angles[j][i]}")
        # Make a list of sorted stars by distance
        for i in range(len(self._stars)):
            dists = []
            for j in range(len(self._stars)):
                if i == j:
                    continue
                # Dist, index
                dists.append((self._star_distances[i][j], j))
            # Sort by distance
            dists = sorted(dists, key=lambda x: x[0])
            self._stars_by_distance.append([d[1] for d in dists])
            _log.debug(f" Star @ idx {i}'s closest stars (cropped to 10 stars): %s"%(", ".join("%i"%i for i in self._stars_by_distance[i][:10])))

    def match_tile(self, tile,
                          max_size_diff = _def_max_size_diff,
                          max_dist_diff = _def_max_dist_diff,
                          max_angle_diff = _def_max_angle_diff,
                          closest_stars_to_check = _def_closest_stars_to_check,
                          stop_after_miss_stars = _def_stop_after_miss_stars,
                          ):
        ''' This algoritm will test each star on the reference map against each start on the tile map
The initial pair of stars (ref_A) is assumed to be the same and a size adjustment factor is
calculated.

Then, each of the {closest_stars_to_check} closest stars for the ref_A star on both the reference
map and the tile map is assumed to match each other. This second assumed star match is ref_B. ref_B stars
will be checked to have the appropiate size. ref_B tile star's adjusted size should no more than 
{max_size_diff}% off based on the max size found on the tile (adjusted with the scale factor).

For each assumed match an scale factor and adjustment angle can be calculated. Once these two are available we
are ready to test all the remaining stars on the tile to have a matching star on the reference following
these rules:

> Matching stars should have
  > a distance error no larger than {max_dist_diff}% of the 
    max distance between any star on the tile (adjusted with the scale factor)
  > a size error no larger than {max_size_diff}% of the 
    max size found on the tile (adjusted with the scale factor)
  > an angle error no larger than {max_angle_diff}% (out of 360
    degrees. This check can be disabled. Is it disabled now? {"Yes" if max_angle_diff is None else "No"}
> A match score is calculated as follows:
  > For each matched star, excluding the two reference stars, 100 points are added
    to the score
  > Percentage differences on size, angle and distance are subtracted from the score
> A count of not matched stars, those found on the tile but not present on the 
  reference map is kept
> Search stops after {stop_after_miss_stars} stars are not found

For each match the following info is saved:
  > match score
  > scaling distance factor
  > scaling size factor
  > angle adjustment
  > Index for these stars:
     > ref_A
     > ref_B
  > List of all the remaining stars on the tile with:
     > Index of star on tile
     > match score, 0 if no match found
     > Index of star on reference, if found

# TODO: add a check to verify how many stars included inside a circle of all matched stars
  at the reference map have no match with any star on the tile side. Define how this affects
  the score.
'''
        # This algoritm will test each star on the reference map against each start on the tile map
        scores = []
        for ref_refA_star in range(len(self._stars)):
            for tile_refA_star in range(len(tile._stars)):
                
                # The initial pair of stars (ref_A) is assumed to be the same and a size adjustment factor is
                # calculated.
                size_adj_factor = self._stars[ref_refA_star][STAR_SZ] / self._stars[tile_refA_star][STAR_SZ]
                tile_max_size_adj = tile._max_size * size_adj_factor
                #max_size_error = tile_max_size_adj * max_size_diff / 100

                _log.debug(f"Comparing refA stars. From ref map: {ref_refA_star}, from tile map: {tile_refA_star}")
                _log.debug(f"  |--> Size adjustment: {size_adj_factor}")
                _log.debug(f"  \\--> Tile max found size adjusted: {tile_max_size_adj}")
                #_log.debug(f"  \\--> Max tolerated size error: {max_size_error}")

                for ref_refB_star in self._stars_by_distance[ref_refA_star][:closest_stars_to_check]:
                    for tile_refB_star in tile._stars_by_distance[tile_refA_star][:closest_stars_to_check]:
                        # Then, each of the {closest_stars_to_check} closest stars for the ref_A star on both the reference
                        # map and the tile map is assumed to match each other. This second assumed star match is ref_B. ref_B stars
                        # will be checked to have the appropiate size. ref_B tile star's adjusted size should no more than 
                        # {max_size_diff}% off based on the max size found on the tile (adjusted with the scale factor).

                        ref_refB_size = self._stars[ref_refB_star][STAR_SZ]
                        tile_refB_adj_size = tile._stars[tile_refB_star][STAR_SZ] * size_adj_factor
                        size_error = (100 * abs(tile_refB_adj_size - ref_refB_size) / ref_refB_size)
                        _log.debug(f"    Comparing to refB stars. From ref map: {ref_refB_star}, from tile map: {tile_refB_star}")
                        _log.debug(f"      |--> Ref_B size from ref map: {ref_refB_size}")
                        _log.debug(f"      |--> Adjusted Ref_B size from tile map: {tile_refB_adj_size}")
                        _log.debug(f"      \\--> Size error: {size_error}%")

                        if size_error > max_size_diff:
                            _log.debug("    Above max size tolerance, skipping...")
                            continue
                        _log.debug("    Under tolerance, continuing...")

                        # For each assumed match an scale factor and adjustment angle can be calculated. 
                        ref_stars_distance = self._star_distances[ref_refA_star][ref_refB_star]
                        tile_adj_stars_distance = tile._star_distances[tile_refA_star][tile_refB_star]
                        tile_scale_factor = ref_stars_distance / tile_adj_stars_distance
                        adj_angle = _adj_angle(self._star_angles[ref_refA_star][ref_refB_star] - tile._star_angles[tile_refA_star][tile_refB_star])
                        tile_max_star_dist_adj = tile._max_distance * tile_scale_factor
                        tile_max_star_size_adj = tile._max_size * tile_scale_factor
                        
                        _log.debug("    Tile comparison parameters:")
                        _log.debug("      |--> Distance adjustment factor: %.4f"%(tile_scale_factor,))
                        _log.debug("      |--> Adjustment angle: %.3f deg"%(adj_angle,))
                        _log.debug("      |--> max star size of stars on tile (adjusted): %.4f"%(tile_max_star_size_adj,))
                        _log.debug("      \\--> max star distance of stars on tile (adjusted): %.4f"%(tile_max_star_dist_adj,))
                        _log.debug("    Comparing all remaining tile stars to match expected angles and distances on ref map stars")

                        score = Score(ref_refA_star, 
                                      ref_refB_star, 
                                      tile_refA_star, 
                                      tile_refB_star,
                                      size_adj_factor,
                                      adj_angle)
                        scores.append(score)

                        # Once these two are available we are ready to test all the remaining stars on the tile to
                        # have a matching star on the reference following these rules:
                        #  
                        #  > Matching stars should have
                        #    > a distance error no larger than {max_dist_diff}% of the 
                        #      max distance between any star on the tile (adjusted with the scale factor)
                        #    > a size error no larger than {max_size_diff}% of the 
                        #      max size found on the tile (adjusted with the scale factor)
                        #    > an angle error no larger than {max_angle_diff}% (out of 360
                        #      degrees. This check can be disabled. Is it disabled now? {"Yes" if max_angle_diff is None else "No"}
                        #  > A match score is calculated as follows:
                        #    > For each matched star, excluding the two reference stars, 100 points are added
                        #      to the score
                        #    > Percentage differences on size and distance are subtracted from the score
                        #  > A count of not matched stars, those found on the tile but not present on the 
                        #    reference map is kept
                        #  > Search stops after {stop_after_miss_stars} stars are not found
                        
                        for tile_test_star in range(len(tile._stars)):
                            # Skip the two reference stars
                            if tile_test_star in (tile_refA_star, tile_refB_star):
                                continue

                            # get adjusted distance and angle to refA and then see if a matching star exists on ref map
                            tile_test_star_adj_dist = tile._star_distances[tile_refA_star][tile_test_star] * tile_scale_factor
                            tile_test_star_adj_angle = tile._star_angles[tile_refA_star][tile_test_star] + adj_angle
                            tile_test_star_adj_size = tile._stars[tile_test_star][STAR_SZ] * tile_scale_factor

                            _log.debug(f"        Finding a match for tile star {tile_test_star}")
                            _log.debug(f"          |--> Tile scale factor: %.4f"%(tile_scale_factor,))
                            _log.debug(f"          |--> adjusted distance to tile A star: {tile_test_star_adj_dist}")
                            _log.debug(f"          |--> adjusted angle to tile A star: {tile_test_star_adj_angle}")

                            # Will test ref map stars by distance from refA star
                            # Don't expect there to be too many stars, tiles should have a handful stars usually
                            # and the ref map will have thousands of stars
                            # So, does not even make sense to try a binary search or something like that
                            # will test in order by distance
                            ref_test_stars_scores = {}
                            for ref_test_star in self._stars_by_distance[ref_refA_star]:
                                ref_test_star_dist = self._star_distances[ref_refA_star][ref_test_star]
                                ref_test_star_size = self._stars[ref_test_star][STAR_SZ]
                                ref_test_star_angle = self._star_angles[ref_refA_star][ref_test_star]

                                ref_test_stars_scores[ref_test_star] = 100

                                _log.debug(f"          | Comparing against ref star {ref_test_star}")

                                # Distance error
                                dist_err = abs(ref_test_star_dist - tile_test_star_adj_dist) * 100 / tile_max_star_dist_adj
                                _log.debug(f"          |   |--> Distance error: {dist_err:.2f}%%")
                                
                                if dist_err > max_dist_diff:
                                    _log.debug(f"          |   \\--> Distance error above limit, score = 0")
                                    ref_test_stars_scores[ref_test_star] = 0
                                    # optimization. If we are above the max tolerated error, stop checks
                                    if ref_test_star_dist > tile_test_star_adj_dist:
                                        break
                                    continue
                                ref_test_stars_scores[ref_test_star] -= dist_err
                                
                                # Size error
                                size_err = abs(ref_test_star_size - tile_test_star_adj_size) * 100 / tile_max_star_size_adj
                                _log.debug(f"          |   |--> Size error: {size_err:.2f}%%")
                                if size_err > max_size_diff:
                                    _log.debug(f"          |   \\--> Size error above limit, score = 0")
                                    ref_test_stars_scores[ref_test_star] = 0
                                    continue
                                ref_test_stars_scores[ref_test_star] -= size_err
                                
                                if max_angle_diff is not None:
                                    angle_error = angle_abs_diff(ref_test_star_angle, tile_test_star_adj_angle) * 100 / 360
                                    _log.debug(f"          |   |--> Angle error: {angle_error:.2f}%%")
                                    if angle_error > max_angle_diff:
                                        _log.debug(f"          |   \\--> Angle error above limit, score = 0")
                                        ref_test_stars_scores[ref_test_star] = 0
                                        continue
                                    ref_test_stars_scores[ref_test_star] -= angle_error
                                else:
                                    _log.debug(f"          |   |--> Angle error: check is disabled")
                                _log.debug(f"          |   \\--> Final star score: {ref_test_stars_scores[ref_test_star]:.2f}")

                            # Register the highest score
                            tile_test_star_score = 0
                            tile_test_star_matching_star = None
                            for st, sc in ref_test_stars_scores.items():
                                if sc > tile_test_star_score:
                                    tile_test_star_score = sc
                                    tile_test_star_matching_star = st
                            _log.debug(f"          |--> tile test star score: {tile_test_star_score:.2f}")
                            _log.debug(f"          \\--> tile test star matched ref star: {tile_test_star_matching_star}")
                            score.register_tile_star_score(tile_test_star, tile_test_star_score, tile_test_star_matching_star)
                        _log.debug(f"    Final score: {score.get_score()}")
        # Sort scores by score
        scores = sorted(scores, key=lambda x: x.get_score(), reverse=True)
        
        max_score = max([score.get_score() for score in scores])
        score_bar_point_size = 80 / max_score
        for idx, score in enumerate(scores):
            score.print_summary(show_hdr = idx == 0, score_bar_point_size = score_bar_point_size, list_matches = idx < 5)
        
        return scores

#  Reference Map A
#   
# 15 |--------------------------------
#    |     .    .    .    .8   .    . 
#    |     .    .    .    .    .7   . 
#    |     .    .    11   .    .    . 
#    |     .    .    .    .    .    . 
# 10 |--------------------------------
#    |     . 3  .13  .  10.    .6   . 
#    |     .    .    1    .    .    . 
#    |     .    .12  .    .    .    . 
#    |     .    .    .   9.    .    . 
# 5  |--------------------------------
#    |     .    2    .    .   5.    . 
#    |     .   0.    .    .    .    . 
#    |     .    .    . 4  .    .    . 
#    |     .    .    .    .    .    . 
# 0  |     .    .    .    .    .    . 
#    \--------------------------------
#     ^    ^    ^    ^    ^    ^    ^ 
#     0    5    10   15   20   25   30
_ref_map_A = (( 9, 3, 1 ), # 0
              (15, 8, 2 ), # 1
              (10, 4, 3 ), # 2
              ( 7, 9, 4 ), # 3
              (17, 2, 5 ), # 4
              (24, 4, 1 ), # 5
              (26, 9, 2 ), # 6
              (26,13, 3 ), # 7
              (21,14, 4 ), # 8
              (19, 6, 5 ), # 9
              (18, 9, 1 ), # A
              (15,12, 2 ), # B
              (11, 7, 3 ), # C
              (11, 9, 4 ), # D
)

# Adjusted to stars 1, 3, 10, 12 and 13 from ref_A with angle 45 and size 3
_tile_map_A_0 = [(14.849242404917497, 48.79036790187178, 6),
                 (-4.242640687119286, 33.941125496954285, 12),
                 (19.091883092036785, 57.27564927611036, 3),
                 (8.48528137423857, 38.18376618407357, 9),
                 (4.242640687119284, 42.42640687119285, 12)]
# A.1: No noise
_tile_map_A_1 = ((20.0, 3.0,12.0), # 0
                 (22.0, 3.0, 9.0), # 1
                 (20.0,10.0, 3.0), # 2
                 (21.0, 7.0, 6.0), # 3
                 (23.0,11.0,15.0), # 4
)
# A.2: translated on X and Y
_tile_map_A_2 = ((40.0,13.0,12.0), # 0
                 (42.0,13.0, 9.0), # 1
                 (40.0,20.0, 3.0), # 2
                 (41.0,17.0, 6.0), # 3
                 (43.0,21.0,15.0), # 4
)

#  tile B.0
#  10 |-----1---------------
#     |     .    .    .    . 
#     |     .    .    .    . 
#     |     .    .    .    . 
#     |     .    .    .    . 
#  5  |----------3----2-------
#     |     .    .    .    . 
#     |     .    .    .    . 
#     |     .    .    .    . 
#     |     .    .    .    . 
#  0  |     .    .    .    . 
#     \-----0-----------------
#      ^    ^    ^    ^    ^ 
#      0    5    10   15   20

_tile_map_B_0 = (( 5.0, 0.0, 1.0), # 0
                 ( 5.0,10.0, 1.0), # 1
                 (15.0, 5.0, 1.0), # 2
                 (10.0, 5.0, 1.0), # 3

)
_tile_map_B_1 = (( 5.1, 0.0, 1.01), # 0
                 ( 5.0, 9.9, 0.98), # 1
                 (14.9, 5.0, 1.03), # 2
                 (10.0, 5.1, 1.00), # 3
)


_test_maps = dict(ref_A = _ref_map_A,
                  tile_A0 = _tile_map_A_0,
                  tile_A1 = _tile_map_A_1,
                  tile_A2 = _tile_map_A_2,
                  tile_B0 = _tile_map_B_0,
                  tile_B1 = _tile_map_B_1,
                  )

def plot_map(map, title):
    import matplotlib.pyplot as plt

    # Separate into x, y, size lists
    x = [d[0] for d in map._stars]
    y = [d[1] for d in map._stars]
    sizes = [300*d[2]/map._max_size for d in map._stars]

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


def main():
    global _log

    parser = argparse.ArgumentParser(description="Mock mode checker options")
    parser.add_argument("-L", "--logfile",          dest="logfile",                 default=None, help="Path to log file")
    parser.add_argument("--ref_map",                dest="ref_map",                 default=None, help="ID for the map to use as reference")
    parser.add_argument("--tile_map",               dest="tile_map",                default=None, help="ID for the map to use as tile")
    parser.add_argument("--max_size_diff",          dest="max_size_diff",           default=_def_max_size_diff,           type=float,    help="Max tolerated star size difference, in percentage. Default: %(default)s%%")
    parser.add_argument("--max_dist_diff",          dest="max_dist_diff",           default=_def_max_dist_diff,           type=float,    help="Max tolerated star distance difference as a percentage of the max distance between any star on the tile (adjusted with the scale factor) Default: %(default)s%%")
    parser.add_argument("--max_angle_diff",         dest="max_angle_diff",          default=_def_max_angle_diff,          type=float,    help="Max tolerated angle error, as a percentage of 360 degrees. Default: %(default)s%%")
    parser.add_argument("--closest_stars_to_check", dest="closest_stars_to_check",  default=_def_closest_stars_to_check,  type=float,    help="Number of stars closest to every tested reference pair of stars on tile and ref map to test matches for. Default: %(default)s")
    parser.add_argument("--stop_after_miss_stars",  dest="stop_after_miss_stars",   default=_def_stop_after_miss_stars,   type=float,    help="Stop after these many stars from the tile are not found on the reference map. Default: %(default)s")
    args =  parser.parse_args()

    if args.ref_map is None or args.ref_map not in _test_maps:
        raise Exception("Pls provide a valid ref_map value. Got %s. Valid: %s"%(args.ref_map, " ".join(_test_maps.keys()),))
    if args.tile_map is None or args.tile_map not in _test_maps:
        raise Exception("Pls provide a valid tile_map value. Got %s. Valid: %s"%(args.tile_map, " ".join(_test_maps.keys()),))
    if args.logfile is None:
        args.logfile = os.path.splitext(os.path.basename(sys.argv[0]))[0] + time.strftime("%y%m%d_%H%M%S") + "__" + args.ref_map + "__vs__" + args.tile_map + ".log"
    _log = init_logger(name = sys.argv[0], 
                    log_file = args.logfile,
                    file_level=logging.DEBUG, 
                    console_level=logging.INFO)
    _log.info("Logger name: %s"%(args.logfile,))

    #stars = []
    #stars.append(_ref_map_A[1])
    #stars.append(_ref_map_A[3])
    #stars.append(_ref_map_A[10])
    #stars.append(_ref_map_A[12])
    #stars.append(_ref_map_A[13])
    #
    #tile_A_0 = StarMap(stars).adjust_to_angle_and_size(adj_angle = 45, size_adj_factor = 3)._stars
    #import pprint
    #pprint.pprint(tile_A_0)
    #return
    
    ref_map = StarMap(_test_maps[args.ref_map])
    tile_map = StarMap(_test_maps[args.tile_map])
    scores = ref_map.match_tile(tile_map,
                                 max_size_diff = args.max_size_diff,
                                 max_dist_diff = args.max_dist_diff,
                                 max_angle_diff = args.max_angle_diff,
                                 closest_stars_to_check = args.closest_stars_to_check,
                                 stop_after_miss_stars = args.stop_after_miss_stars,
                                )

    plot_map(ref_map, "Reference Map")
    plot_map(tile_map, "Tile Map")

    # s = types.SimpleNamespace()
    # s.size_adj_factor = 1
    # s.adj_angle = 270   
    # tile_rotated = tile_map.adjust_to_score(s)
    # plot_map(tile_rotated, "Tile Map rotated")


    for score in scores[:3]:
        adj_map = tile_map.adjust_to_score(score)
        plot_map(adj_map, "Adjusted solution with score %.3f"%(score.get_score(), ))

    input()




if __name__ == "__main__":
    main()


