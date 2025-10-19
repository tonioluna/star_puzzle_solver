import sys
import pickle
import logging
import os
import cv2
import argparse
import time
from matplotlib import pyplot as plt
import numpy as np

import star_map
import star_finder
import perf_recorder as _pr

pr = _pr.get_perf_recorder()

#import numpy as np
#from scipy.spatial.distance import cdist
#from scipy.optimize import linear_sum_assignment

solution_colors = (
    (255, 0, 0),       # Red
    (255, 69, 0),      # Orange-Red
    (255, 140, 0),     # Orange
    (255, 215, 0),     # Golden Yellow
    (255, 255, 0),     # Yellow
    (173, 255, 47),    # Yellow-Green
    (0, 255, 0),       # Lime Green
    (0, 255, 127),     # Spring Green
    (0, 206, 209),     # Medium Aquamarine
    (0, 200, 0),       # Bright Green
)

def draw_matches(image_path, 
                 ref_map,
                 scores
                ):

    _log.info("Loading image...")
    image = cv2.imread(image_path)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Restore 3 channels so we can draw in color!
    image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    _log.info("  \\--> Done!")
    
    stars = []
    star_colors = {}
    
    for score_idx, score in enumerate(scores):
        sl = [r for t,r in score._mappings.items() if r is not None]
        stars.extend(sl)
        for s in sl:
            if s not in star_colors:
                if score_idx >= len(solution_colors):
                    c = solution_colors[-1]
                else:
                    c = solution_colors[score_idx]
                star_colors[s] = c
    stars = list(set(stars))

    for s in stars:
        i = ref_map._stars[s]
        
        if ref_map.from_pic_y_correction is not None:
            i = list(i)
            i[1] = ref_map.from_pic_y_correction - i[1]

        i = [int(x) for x in i]
        # Draw the outer circle
        cv2.circle(image, (i[0], i[1]), i[2], star_colors[s], 2)
        # Draw the center of the circle
        #cv2.circle(image, (i[0], i[1]), 2, (0, 0, 255), 2)

    plt.figure(figsize=(6, 6))
    plt.title("Matched Stars")
    plt.show(block = False)
    plt.imshow(image)

def match_images(reference_image, 
                 tile_image,
                 show_images = False,
                 exp_tile_count = None,
                 exp_scale_factor = None,
                 angle_rotation_ranges = None):
    
    pr.record_checkpoint("match_images() start")

    A = star_finder.find_stars(reference_image,
                           show_images=show_images)
    B = star_finder.find_stars(tile_image,
                            show_images=show_images,
                            gray_filter_threshold = 120)

    _log.info("Ref image has %i stars"%(len(A),))
    _log.info("Tile image has %i stars"%(len(B),))

    pr.record_checkpoint("match_images() building start map for reference pic")
    ref_map = star_map.StarMap(A, from_picture = True,
                               exp_tile_count = exp_tile_count,
                               source_picture = os.path.abspath(reference_image))
    
    pr.record_checkpoint("match_images() building start map for tile")
    tile_map = star_map.StarMap(B, from_picture = True,
                                source_picture = os.path.abspath(tile_image))

    pr.record_checkpoint("match_images() matching tile")
    scores = ref_map.match_tile(tile_map,
                                exp_scale_factor = exp_scale_factor,
                                angle_rotation_ranges = angle_rotation_ranges,
                                )

    star_map.plot_map(ref_map, "Reference Map")
    star_map.plot_map(tile_map, "Tile Map")

    # s = types.SimpleNamespace()
    # s.size_adj_factor = 1
    # s.adj_angle = 270   
    # tile_rotated = tile_map.adjust_to_score(s)
    # plot_map(tile_rotated, "Tile Map rotated")

    if scores is not None:
        for idx, score in enumerate(scores[:3]):
            adj_map = tile_map.adjust_to_score(score)
            #star_map.plot_map(adj_map, "Adjusted solution with score %.3f"%(score.score, ))
            star_map.plot_map(adj_map, "Adjusted solution %i. score: %.3f, size: %.3f, angle: %.2f"%(idx, score.score, score.size_adj_factor, score.adj_angle))

        draw_matches(reference_image, 
                     ref_map,
                     scores[:10])
    

def main():
    global _log

    parser = argparse.ArgumentParser(description="Mock mode checker options")
    parser.add_argument("-L", "--logfile",          dest="logfile",                 default=None, help="Path to log file")
    parser.add_argument("--reference_image",        dest="reference_image",         default=None, help="ID for the map to use as reference")
    parser.add_argument("--tile_image",             dest="tile_image",              default=None, help="ID for the map to use as tile")
    parser.add_argument("--exp_ref_tile_count",     dest="exp_ref_tile_count",      default=None, type=star_map.arg_x_y_count,       help="Expected count of X and Y tiles/puzzle pieces on the template/reference map. Default: %(default)s%%")
    parser.add_argument("--exp_tile_scale_factor",  dest="exp_tile_scale_factor",   default=None, type=star_map.arg_scale_factor,    help="Expected scale factor range for the provided tile. Default: %(default)s%%")
    parser.add_argument("--rot_90deg_range",        dest="rot_90deg_range",         default=None, type=star_map.arg_rot_90deg_range, help="Limit the max deviation from 90 degrees the tile can have. Default: %(default)s")
    parser.add_argument("--show_debug_images",      dest="show_debug_images",       default=None, action = "store_true",             help="Show debug images generated when finding starts on the input pictures")
    args =  parser.parse_args()

    if args.logfile is None:
        logs_dir =os.path.join(os.getcwd(), "LOGS")
        if not os.path.exists(logs_dir):
            os.mkdir(logs_dir)
        args.logfile = os.path.join(logs_dir, os.path.splitext(os.path.basename(sys.argv[0]))[0] + time.strftime("%y%m%d_%H%M%S") + ".log")
    _log = star_map.init_logger(name = sys.argv[0], 
                    log_file = args.logfile,
                    file_level=logging.DEBUG, 
                    console_level=logging.INFO)
    star_finder._log = _log
    _pr._log = _log
    
    _log.info("Logger name: %s"%(args.logfile,))

    try:
        pr.record_checkpoint('match_images() call')
        match_images(args.reference_image, 
                        args.tile_image,
                        show_images=args.show_debug_images,
                        exp_tile_count = args.exp_ref_tile_count,
                        exp_scale_factor = args.exp_tile_scale_factor,
                        angle_rotation_ranges = args.rot_90deg_range)
    finally:
        pr.dump()
    #match_images("reference_0.jpg", "fake_tile_1.jpg", show_images=True)
    input("Hit ENTER to exit!")

if __name__ == "__main__":
    main()