import math
import sys
import os
import time

DBG_LVL_NONE = 0
DBG_LVL_BASIC = 1
DBG_LVL_ALL = 2

DBG_LVL = DBG_LVL_ALL
#DBG_LVL = DBG_LVL_NONE

CLOSEST_STARS_INITIAL_CHECK = 3
MAX_DISTANCE_DIFFERENCE_FOR_MATCH = 50
MAX_SIZE_DIFFERENCE_FOR_MATCH = 50
STOP_AFTER_MISSING_STARS = 5
# Set to None to skip angle comparison
#MAX_ANGLE_DIFFERENCE_FOR_MATCH = 10
MAX_ANGLE_DIFFERENCE_FOR_MATCH = None

STAR_X = 0
STAR_Y = 1
STAR_SZ = 2

import logging

def init_logger(name: str, log_file: str, file_level=logging.INFO, console_level=logging.DEBUG):
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

    return logger

log_file = os.path.splitext(os.path.basename(sys.argv[0]))[0] + time.strftime("%y%m%d_%H%M%S") + ".log"
_log = init_logger(name = sys.argv[0], 
                   log_file = log_file,
                   file_level=logging.DEBUG, 
                   console_level=logging.INFO)
_log.info("Logger name: %s"%(log_file,))

def _adj_angle(a):
    if a >= 360:
        return a % 360
    while a < 0:
        a += 360
    return a

def angle_abs_diff(a, b):
    d = abs(a - b)
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
    
    def register_tile_star_score(self, star, score):
        self._tile_star_scores[star] = score

    def get_score(self):
        return sum(self._tile_star_scores.values())

    def print_summary(self, show_hdr):
        if show_hdr:
            _log.info("Ref Map--\  Tile Map-\  Size    Adj")
            _log.info("RefA  RefB  RefA  RefB  Factor  Angle   Score")
        _log.info(f"{self.ref_refA_star:4}  "
                  f"{self.ref_refB_star:4}  "
                  f"{self.tile_refA_star:4}  "
                  f"{self.tile_refB_star:4}  "
                  f"{self.size_adj_factor:6.3f}  "
                  f"{self.adj_angle:6.1f}  "
                  f"{self.get_score():5}  "
                  )

class StarMap:
    def __init__(self, stars):
        self._stars = stars
        self._star_distances = None
        self._star_angles = None
        self._max_distance = None
        self._max_size = None
        self._stars_by_distance = None
        self._build_map()

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
            _log.debug(f" Star @ idx {i}'s {CLOSEST_STARS_INITIAL_CHECK} closest stars: %s"%(", ".join("%i"%i for i in self._stars_by_distance[i])))

    def _match_tile(self, tile):
        f''' This algoritm will test each star on the reference map against each start on the tile map
The initial pair of stars (ref_A) is assumed to be the same and a size adjustment factor is
calculated.

Then, each of the {CLOSEST_STARS_INITIAL_CHECK} closest stars for the ref_A star on both the reference
map and the tile map is assumed to match each other. This second assumed star match is ref_B. ref_B stars
will be checked to have the appropiate size. ref_B tile star's adjusted size should no more than 
{MAX_SIZE_DIFFERENCE_FOR_MATCH}% off based on the max size found on the tile (adjusted with the scale factor).

For each assumed match an scale factor and adjustment angle can be calculated. Once these two are available we
are ready to test all the remaining stars on the tile to have a matching star on the reference following
these rules:

> Matching stars should have
  > a distance error no larger than {MAX_DISTANCE_DIFFERENCE_FOR_MATCH}% of the 
    max distance between any star on the tile (adjusted with the scale factor)
  > a size error no larger than {MAX_SIZE_DIFFERENCE_FOR_MATCH}% of the 
    max size found on the tile (adjusted with the scale factor)
  > an angle error no larger than {MAX_ANGLE_DIFFERENCE_FOR_MATCH}% (out of 360
    degrees. This check can be disabled. Is it disabled now? {"Yes" if MAX_ANGLE_DIFFERENCE_FOR_MATCH is None else "No"}
> A match score is calculated as follows:
  > For each matched star, excluding the two reference stars, 100 points are added
    to the score
  > Percentage differences on size, angle and distance are subtracted from the score
> A count of not matched stars, those found on the tile but not present on the 
  reference map is kept
> Search stops after {STOP_AFTER_MISSING_STARS} stars are not found

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
                max_size_error = tile_max_size_adj * MAX_SIZE_DIFFERENCE_FOR_MATCH / 100

                _log.debug(f"Comparing refA stars. From ref map: {ref_refA_star}, from tile map: {tile_refA_star}")
                _log.debug(f"  |--> Size adjustment: {size_adj_factor}")
                _log.debug(f"  |--> Tile max found size adjusted: {tile_max_size_adj}")
                _log.debug(f"  \\--> Max tolerated size error: {max_size_error}")

                tile_test_star_scores = {}
                for ref_refB_star in self._stars_by_distance[ref_refA_star][:CLOSEST_STARS_INITIAL_CHECK]:
                    for tile_refB_star in tile._stars_by_distance[tile_refA_star][:CLOSEST_STARS_INITIAL_CHECK]:
                        # Then, each of the {CLOSEST_STARS_INITIAL_CHECK} closest stars for the ref_A star on both the reference
                        # map and the tile map is assumed to match each other. This second assumed star match is ref_B. ref_B stars
                        # will be checked to have the appropiate size. ref_B tile star's adjusted size should no more than 
                        # {MAX_SIZE_DIFFERENCE_FOR_MATCH}% off based on the max size found on the tile (adjusted with the scale factor).

                        ref_refB_size = self._stars[ref_refB_star][STAR_SZ]
                        tile_refB_adj_size = tile._stars[tile_refB_star][STAR_SZ] * size_adj_factor
                        _log.debug(f"    Comparing to refB stars. From ref map: {ref_refB_star}, from tile map: {tile_refB_star}")
                        _log.debug(f"      |--> Ref_B size from ref map: {ref_refB_size}")
                        _log.debug(f"      \\--> Adjusted Ref_B size from tile map: {tile_refB_adj_size}")

                        
                        if abs(tile_refB_adj_size - ref_refB_size) > max_size_error:
                            if DBG_LVL >= DBG_LVL_ALL:
                                _log.debug("    Above max size tolerance, skipping...")
                            continue
                        if DBG_LVL >= DBG_LVL_ALL:
                            _log.debug("    Under tolerance, continuing...")

                        # For each assumed match an scale factor and adjustment angle can be calculated. 
                        ref_stars_distance = self._star_distances[ref_refA_star][ref_refB_star]
                        tile_adj_stars_distance = tile._star_distances[tile_refA_star][tile_refB_star]
                        tile_scale_factor = ref_stars_distance / tile_adj_stars_distance
                        adj_angle = self._star_angles[ref_refA_star][ref_refB_star] - tile._star_angles[tile_refA_star][tile_refB_star]
                        tile_max_star_dist_adj = tile._max_distance * tile_scale_factor / 100
                        tile_max_star_size_adj = tile._max_size * tile_scale_factor / 100
                        
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
                        #    > a distance error no larger than {MAX_DISTANCE_DIFFERENCE_FOR_MATCH}% of the 
                        #      max distance between any star on the tile (adjusted with the scale factor)
                        #    > a size error no larger than {MAX_SIZE_DIFFERENCE_FOR_MATCH}% of the 
                        #      max size found on the tile (adjusted with the scale factor)
                        #    > an angle error no larger than {MAX_ANGLE_DIFFERENCE_FOR_MATCH}% (out of 360
                        #      degrees. This check can be disabled. Is it disabled now? {"Yes" if MAX_ANGLE_DIFFERENCE_FOR_MATCH is None else "No"}
                        #  > A match score is calculated as follows:
                        #    > For each matched star, excluding the two reference stars, 100 points are added
                        #      to the score
                        #    > Percentage differences on size and distance are subtracted from the score
                        #  > A count of not matched stars, those found on the tile but not present on the 
                        #    reference map is kept
                        #  > Search stops after {STOP_AFTER_MISSING_STARS} stars are not found
                        
                        for tile_test_star in range(len(tile._stars)):
                            # Skip the two reference stars
                            if tile_test_star in (tile_refA_star, tile_refB_star):
                                continue

                            # get adjusted distance and angle to refA and then see if a matching star exists on ref map
                            tile_test_star_adj_dist = tile._star_distances[tile_refA_star][tile_test_star] * tile_scale_factor
                            tile_test_star_adj_angle = tile._star_angles[tile_refA_star][tile_test_star] * adj_angle
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
                                
                                if dist_err > MAX_DISTANCE_DIFFERENCE_FOR_MATCH:
                                    _log.debug(f"          |   \\--> Distance error above limit, score = 0")
                                    ref_test_stars_scores[ref_test_star] = 0
                                    # optimization. If we are above the max tolerated error, stop checks
                                    if ref_test_star_dist > tile_test_star_adj_dist:
                                        break
                                    continue
                                ref_test_stars_scores[ref_test_star] - dist_err
                                
                                # Size error
                                size_err = abs(ref_test_star_size - tile_test_star_adj_size) * 100 / tile_max_star_size_adj
                                _log.debug(f"          |   |--> Size error: {size_err:.2f}%%")
                                if size_err > MAX_SIZE_DIFFERENCE_FOR_MATCH:
                                    _log.debug(f"          |   \\--> Size error above limit, score = 0")
                                    ref_test_stars_scores[ref_test_star] = 0
                                    continue
                                ref_test_stars_scores[ref_test_star] - size_err
                                
                                if MAX_ANGLE_DIFFERENCE_FOR_MATCH is not None:
                                    angle_error = angle_abs_diff(ref_test_star_angle - tile_test_star_adj_angle) * 100 / 360
                                    _log.debug(f"          |   |--> Angle error: {angle_error:.2f}%%")
                                    if angle_error > MAX_ANGLE_DIFFERENCE_FOR_MATCH:
                                        _log.debug(f"          |   \\--> Angle error above limit, score = 0")
                                        ref_test_stars_scores[ref_test_star] = 0
                                        continue
                                    ref_test_stars_scores[ref_test_star] - angle_error
                                else:
                                    _log.debug(f"          |   |--> Angle error: check is disabled")
                                _log.debug(f"          |   \\--> Final star score: {ref_test_stars_scores[ref_test_star]:.2f}")

                            # Register the highest score
                            tile_test_star_score = max(ref_test_stars_scores.values())
                            _log.debug(f"          \\--> tile test star score: {tile_test_star_score:.2f}")
                            score.register_tile_star_score(tile_test_star, tile_test_star_score)
        first = True
        for score in scores:
            score.print_summary(show_hdr = first)
            if first:
                first = False

#  Reference Map A
#   
# 15 |--------------------------------
#    |     .    .    .    .8   .    . 
#    |     .    .    .    .    .7   . 
#    |     .    .    B    .    .    . 
#    |     .    0    .    .    .    . 
# 10 |--------------------------------
#    |     . 3  .D   .  A .    .6   . 
#    |     .    .    1    .    .    . 
#    |     .    .C   .    .    .    . 
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
#  tile A.0
#  All stars in a box match. right: Using the same numbers as above for ease of match
#  Differences of +/- 0.1 were added to some coordinates and sizes
#  Magnitud was multiplied by 3
#
#  15 |--------------------------------  15 |--------------------------------
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#     |     .    .    .    .  4 .    .      |     .    .    .    .  9 .    . 
#  10 |--------------------2-----------  10 |--------------------A-----------
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#     |     .    .    .    .3   .    .      |     .    .    .    .1   .    . 
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#  5  |--------------------------------  5  |--------------------------------
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#     |     .    .    .    0 1  .    .      |     .    .    .    D C  .    . 
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#     |     .    .    .    .    .    .      |     .    .    .    .    .    . 
#  0  |     .    .    .    .    .    .   0  |     .    .    .    .    .    . 
#     \--------------------------------     \--------------------------------
#      ^    ^    ^    ^    ^    ^    ^       ^    ^    ^    ^    ^    ^    ^ 
#      0    5    10   15   20   25   30      0    5    10   15   20   25   30

_tile_map_A_0 = ((20.1, 3.0,12.2), # 0
                 (21.9, 3.0, 8.8), # 1
                 (20.1,10.0, 3.0), # 2
                 (21.0, 7.1, 5.7), # 3
                 (23.1,10.9,15.3), # 4
)
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

def test_a():
    #ref_map = StarMap(_ref_map_A)
    #ref_map = StarMap(_tile_map_A_1)
    ref_map = StarMap(_tile_map_A_0)
    tile = StarMap(_tile_map_A_0)
    #tile = StarMap(_tile_map_A_1)
    #tile = StarMap(_tile_map_A_2)

    ref_map._match_tile(tile)

test_a()
