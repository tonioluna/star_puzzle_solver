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

STAR_X = star_map.STAR_X
STAR_Y = star_map.STAR_Y
STAR_SZ = star_map.STAR_SZ


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
# 
# def draw_matches(image_path, 
#                  ref_map,
#                  scores
#                 ):
# 
#     _log.info("Loading image...")
#     image = cv2.imread(image_path)
#     image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#     # Restore 3 channels so we can draw in color!
#     image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
#     _log.info("  \\--> Done!")
#     
#     stars = []
#     star_colors = {}
#     
#     for score_idx, score in enumerate(scores):
#         _log.info("Score IDX %i has score %.3f"%(score_idx, score.score,))
#         sl = [r for t,r in score._mappings.items() if r is not None]
#         stars.extend(sl)
#         for s in sl:
#             if s not in star_colors:
#                 if score_idx >= len(solution_colors):
#                     c = solution_colors[-1]
#                 else:
#                     c = solution_colors[score_idx]
#                 star_colors[s] = c
#         #break
#     stars = list(set(stars))
# 
#     for s in stars:
#         i = ref_map._stars[s]
#         
#         if ref_map.from_pic_y_correction is not None:
#             i = list(i)
#             i[1] = ref_map.from_pic_y_correction - i[1]
# 
#         i = [int(x) for x in i]
#         # Draw the outer circle
#         cv2.circle(image, (i[0], i[1]), i[2], star_colors[s], 2)
#         # Draw the center of the circle
#         #cv2.circle(image, (i[0], i[1]), 2, (0, 0, 255), 2)
# 
#     plt.figure(figsize=(6, 6))
#     plt.title("Matched Stars")
#     plt.show(block = False)
#     plt.imshow(image)

def draw_matches(image_path, 
                 ref_map,
                 scores,
                 paused_plot = False,
                ):

    for score_idx, score in enumerate(scores):
        _log.info("Score IDX %i has score %.3f"%(score_idx, score.score,))
        
        _log.info("Loading image...")
        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Restore 3 channels so we can draw in color!
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        _log.info("  \\--> Done!")
        
        star_colors = {}
        
        stars = score.get_matched_templ_stars()
        for s in stars:
            if s not in star_colors:
                #if score_idx >= len(solution_colors):
                #    c = solution_colors[-1]
                #else:
                #    c = solution_colors[score_idx]
                #star_colors[s] = c
                star_colors[s] = solution_colors[0]
            #break
        
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
        plt.title("Matched Stars for score %.2f"%(score.score,))
        plt.show(block = False)
        plt.imshow(image)

        if paused_plot:
            input("Hit ENTER to show the next solution. Will close this one.")
            plt.close()

def draw_comparisons(image_path, 
                     tile_path,
                 ref_map,
                 tile_map,
                 scores,
                 paused_plot = False,
                ):

    for score_idx, score in enumerate(scores):
        _log.info("Plotting comparison %i with score %.3f"%(score_idx, score.score,))
        
        _log.info("Loading image...")
        image = cv2.imread(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        height, width = image.shape

        # Now, let's cut the part of the image that has the matched stars
        min_x = min_y = max_x = max_y = None
        #matched_stars = score.get_matched_templ_stars()
        tile_to_templ_map = score.get_all_tile_to_templ_pairs()
        for _s in tile_to_templ_map.values():
            # Not all tile stars get matched to a template star
            if _s is None: continue
            s = ref_map._stars[_s]

            min_x = s[STAR_X] if min_x is None else min(min_x, s[STAR_X])
            max_x = s[STAR_X] if max_x is None else max(max_x, s[STAR_X])
            min_y = s[STAR_Y] if min_y is None else min(min_y, s[STAR_Y])
            max_y = s[STAR_Y] if max_y is None else max(max_y, s[STAR_Y])
        
        # Adjust coordinates to crop template leaving a 25% margin
        d_x = (max_x - min_x)
        d_y = (max_y - min_y)
        min_x -= d_x * 0.25
        max_x += d_x * 0.25
        min_y -= d_y * 0.25
        max_y += d_y * 0.25
        # Limit to pic dimmensions
        min_x = int(max(0, min_x))
        min_y = int(max(0, min_y))
        max_y = int(min(max_y, height))
        max_x = int(min(max_x, width))

        # Crop the image!
        _log.debug("Cropping image")
        _log.debug("  |--> min_x: %s"%(repr(min_x),))
        _log.debug("  |--> max_x: %s"%(repr(max_x),))
        _log.debug("  |--> min_y: %s"%(repr(min_y),))
        _log.debug("  \\--> max_y: %s"%(repr(max_y),))
        image = image[min_y:max_y, min_x:max_x]

        # Restore 3 channels so we can draw in color!
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        _log.info("  \\--> Done!")
        
        # Draw template stars
        for s in tile_to_templ_map.values():
            if s is None: continue
            i = ref_map._stars[s]
            
            if ref_map.from_pic_y_correction is not None:
                i = list(i)
                i[1] = ref_map.from_pic_y_correction - i[1]

            i = [int(x) for x in i]
            # Draw the outer circle
            cv2.circle(image, (i[0] - min_x, i[1] - min_y), i[2], solution_colors[0], 2)
            # Draw the center of the circle
            #cv2.circle(image, (i[0], i[1]), 2, (0, 0, 255), 2)
        
        # Draw tile stars, 
        adj_tile_map = tile_map.adjust_to_score(score)

        for s in tile_to_templ_map.keys():
            i = adj_tile_map._stars[s]
            
            if adj_tile_map.from_pic_y_correction is not None:
                i = list(i)
                i[1] = adj_tile_map.from_pic_y_correction - i[1]

            i = [int(x) for x in i]
            # Draw the outer circle
            cv2.circle(image, (i[0] - min_x, i[1] - min_y), i[2], solution_colors[-1], 1)
            # Draw the center of the circle
            #cv2.circle(image, (i[0], i[1]), 2, (0, 0, 255), 2)
        

        plt.figure(figsize=(6, 6))
        plt.title("Matched Stars for score %.2f"%(score.score,))
        plt.show(block = False)
        plt.imshow(image)

        if paused_plot:
            input("Hit ENTER to show the next solution. Will close this one.")
            plt.close()

def match_images(reference_image, 
                 tile_image,
                 show_images = False,
                 exp_tile_count = None,
                 exp_scale_factor = None,
                 angle_rotation_ranges = None,
                 dump_maps = False, 
                 plot_input_maps = False,
                 plot_solution_maps = None,
                 draw_matches_count = None,
                 draw_comparisons_count = None,
                 force_scan_ref = False,
                 force_scan_tile = False,
                 force_map_ref = False,
                 force_map_tile = False,  
                 unmatched_stars_weight = False,        
                 max_listed_results = 25,       
                 tile_min_circle_radius = 2,
                 tile_max_circle_radius = 20,
                 tile_gray_filter_threshold = 164,
                 tile_min_dist_between_circles = 5,
                 templ_gray_filter_threshold = 164,
                 paused_plot = False,
                 ):
    
    plt.close("ALL")

    pr.record_checkpoint("match_images() start")

    A, A_pickle = star_finder.find_stars(reference_image,
                           show_images=show_images,
                           force_scan = force_scan_ref,
                           gray_filter_threshold=templ_gray_filter_threshold)
    B, B_pickle = star_finder.find_stars(tile_image,
                            show_images=show_images,
                            force_scan = force_scan_tile,
                            min_circle_radius=tile_min_circle_radius,
                            max_circle_radius=tile_max_circle_radius,
                            gray_filter_threshold=tile_gray_filter_threshold,
                            min_dist_between_circles=tile_min_dist_between_circles)

    _log.info("Ref image has %i stars"%(len(A),))
    _log.info("Tile image has %i stars"%(len(B),))

    pr.record_checkpoint("match_images() building start map for reference pic")
    _log.info("Creating a star map for reference image")
    ref_map = star_map.StarMap(A, from_picture = True,
                               exp_tile_count = exp_tile_count,
                               stars_pickle=A_pickle,
                               force_scan = force_map_ref)
    
    pr.record_checkpoint("match_images() building start map for tile")
    _log.info("Creating a star map for tile image")
    tile_map = star_map.StarMap(B, from_picture = True,
                                stars_pickle = B_pickle,
                               force_scan = force_map_tile)

    pr.record_checkpoint("match_images() matching tile")
    scores = ref_map.match_tile(tile_map,
                                exp_scale_factor = exp_scale_factor,
                                angle_rotation_ranges = angle_rotation_ranges,
                                unmatched_stars_weight = unmatched_stars_weight,
                                max_listed_results = max_listed_results,
                                )

    if plot_input_maps:
        star_map.plot_map(ref_map, "Reference Map")
        star_map.plot_map(tile_map, "Tile Map")

    # s = types.SimpleNamespace()
    # s.size_adj_factor = 1
    # s.adj_angle = 270   
    # tile_rotated = tile_map.adjust_to_score(s)
    # plot_map(tile_rotated, "Tile Map rotated")

    if scores is not None:
        if plot_solution_maps is not None:
            for idx, score in enumerate(scores[:plot_solution_maps]):
                adj_map = tile_map.adjust_to_score(score)
                #star_map.plot_map(adj_map, "Adjusted solution with score %.3f"%(score.score, ))
                star_map.plot_map(adj_map, "Adjusted solution %i. score: %.3f, size: %.3f, angle: %.2f"%(idx, score.score, score.size_adj_factor, score.adj_angle))

        if draw_matches_count is not None:
            draw_matches(reference_image, 
                        ref_map,
                        scores[:draw_matches_count], 
                        paused_plot = paused_plot)
        if draw_comparisons_count is not None:
            draw_comparisons(reference_image, 
                             tile_image,
                             ref_map,
                             tile_map,
                             scores[:draw_comparisons_count], 
                             paused_plot = paused_plot)

    
    if dump_maps:
        ref_map.dump_map("ref_map")
        tile_map.dump_map("tile_map")

    #import pdb
    #pdb.set_trace()

def main():
    global _log
    global args

    parser = argparse.ArgumentParser(description="Mock mode checker options")
    parser.add_argument("-L", "--logfile",          dest="logfile",                 default=None, help="Path to log file")
    parser.add_argument("--reference_image",        dest="reference_image",         default=None, help="ID for the map to use as reference")
    parser.add_argument("--tile_image",             dest="tile_image",              default=None, help="ID for the map to use as tile")
    parser.add_argument("--exp_ref_tile_count",     dest="exp_ref_tile_count",      default=None, type=star_map.arg_x_y_count,       help="Expected count of X and Y tiles/puzzle pieces on the template/reference map. Default: %(default)s%%")
    parser.add_argument("--exp_tile_scale_factor",  dest="exp_tile_scale_factor",   default=None, type=star_map.arg_scale_factor,    help="Expected scale factor range for the provided tile. Default: %(default)s%%")
    parser.add_argument("--rot_90deg_range",        dest="rot_90deg_range",         default=None, type=star_map.arg_rot_90deg_range, help="Limit the max deviation from 90 degrees the tile can have. Default: %(default)s")
    parser.add_argument("--show_debug_images",      dest="show_debug_images",       default=None, action = "store_true",             help="Show debug images generated when finding starts on the input pictures")
    parser.add_argument("--dump_maps",              dest="dump_maps",               default=None, action = "store_true",             help="Dump reference and tile maps on python format for manual analysis")
    parser.add_argument("--debug",                  dest="debug",                   default=None, action = "store_true",             help="Save debug messages into the file logger")
    parser.add_argument("--full_debug",             dest="full_debug",              default=None, action = "store_true",             help="Same as --force_debug --debug")
    parser.add_argument("--solution_debug",         dest="solution_debug",          default=None, action = "store_true",             help="Dump lots and lots of debug messages while solving the maps.")
    parser.add_argument("--plot_input_maps",        dest="plot_input_maps",         default=None, action = "store_true",             help="Plot input map diagrams (tile and reference) showing the star numbers")
    parser.add_argument("--force_scan_ref",         dest="force_scan_ref",          default=None, action = "store_true",             help="Force scanning images and ignore existing pickle files (which will be re-regenerated) for ref")
    parser.add_argument("--force_scan_tile",        dest="force_scan_tile",         default=None, action = "store_true",             help="Force scanning images and ignore existing pickle files (which will be re-regenerated) for tile")
    parser.add_argument("--force_map_ref",          dest="force_map_ref",           default=None, action = "store_true",             help="Force full start map scanning instead of loading an existing pickle file (which will be re-regenerated) for ref")
    parser.add_argument("--force_map_tile",         dest="force_map_tile",          default=None, action = "store_true",             help="Force full start map scanning instead of loading an existing pickle file (which will be re-regenerated) for tile")
    parser.add_argument("--unmatched_stars_weight", dest="unmatched_stars_weight",  default=50, type = float,                        help="Weight to use when applying unmatched stars ratio. 0 to 100 where 100 is a direct multiplication of the ratio to the score and 0 is no effect or the ratio")
    parser.add_argument("--plot_solution_maps",     dest="plot_solution_maps",      default=None, type = int,                        help="Number of solution maps to plot (as diagrams)")
    parser.add_argument("--draw_matches",           dest="draw_matches",            default=None, type = int,                        help="Number of solution images to display showing the matched stars")
    parser.add_argument("--tile_gray_filter_threshold",  dest="tile_gray_filter_threshold",  default=128, type = int,                help="tile_gray_filter_threshold")
    parser.add_argument("--templ_gray_filter_threshold",  dest="templ_gray_filter_threshold",  default=128, type = int,                help="templ_gray_filter_threshold")
    parser.add_argument("--draw_comparisons",           dest="draw_comparisons",            default=None, type = int,                        help="Number of solution images to display showing the matched stars")
    parser.add_argument("--interactive",            dest="interactive",             default=None, action = "store_true",             help="Run an interactive shell")
    args =  parser.parse_args()

    if args.full_debug:
        args.solution_debug = True
        args.debug = True
        args.force_scan_ref = True
        args.force_scan_tile = True
        args.force_map_ref = True
        args.force_map_tile = True

    if args.logfile is None:
        logs_dir =os.path.join(os.getcwd(), "LOGS")
        if not os.path.exists(logs_dir):
            os.mkdir(logs_dir)
        args.logfile = os.path.join(logs_dir, os.path.splitext(os.path.basename(sys.argv[0]))[0] + time.strftime("%y%m%d_%H%M%S") + ".log")
    _log = star_map.init_logger(name = sys.argv[0], 
                    log_file = args.logfile,
                    file_level=logging.DEBUG if args.debug else logging.INFO, 
                    console_level=logging.INFO)
    star_finder._log = _log
    star_map.DBG = args.solution_debug
    _pr._log = _log
    assert args.plot_solution_maps is None or args.plot_solution_maps > 0, "--plot_solution_maps must be positive"
    assert args.draw_matches is None or args.draw_matches > 0, "--draw_matches must be positive"
    assert args.draw_comparisons is None or args.draw_comparisons > 0, "--draw_comparisons must be positive"
    
    _log.info("Logger name: %s"%(args.logfile,))
    _log.info("Command Line: %s %s"%(sys.executable, " ".join([a if " " not in a else repr(a) for a in sys.argv]),))

    if args.interactive:
        return run_interactive()

    try:
        pr.record_checkpoint('match_images() call')
        t0 = time.time()
        match_images(args.reference_image, 
                        args.tile_image,
                        show_images = args.show_debug_images,
                        exp_tile_count = args.exp_ref_tile_count,
                        exp_scale_factor = args.exp_tile_scale_factor,
                        angle_rotation_ranges = args.rot_90deg_range,
                        dump_maps = args.dump_maps,
                        plot_input_maps = args.plot_input_maps,
                        plot_solution_maps = args.plot_solution_maps,
                        draw_matches_count = args.draw_matches,
                        draw_comparisons_count = args.draw_comparisons,
                        force_scan_ref = args.force_scan_ref,
                        force_scan_tile = args.force_scan_tile,
                        force_map_ref = args.force_map_ref,
                        force_map_tile = args.force_map_tile,
                        unmatched_stars_weight = args.unmatched_stars_weight,
                        tile_gray_filter_threshold = args.tile_gray_filter_threshold,
                        templ_gray_filter_threshold = args.templ_gray_filter_threshold,

                        )
        t1 = time.time()
        _log.info("Match images took %s"%(_pr._fmt_time(t1 - t0),))
    finally:
        pr.dump()
        _log.info("Command line: %s"%(" ".join(sys.argv)))
        _log.info("Logfile: %s"%(args.logfile,))
    input("Hit ENTER to exit!")

def show_tile(tile_image,
              show_images = True,
              force_scan = False,
              force_map = False,
              dump = True,
              tile_min_circle_radius = 2,
              tile_max_circle_radius = 20,
              tile_min_dist_between_circles = 15,
              gray_filter_threshold = 164,
              ):
    A, A_pickle = star_finder.find_stars(tile_image,
                           show_images=show_images,
                           force_scan=force_scan,
                           gray_filter_threshold = gray_filter_threshold,
                           min_circle_radius=tile_min_circle_radius,
                           max_circle_radius=tile_max_circle_radius,
                           min_dist_between_circles=tile_min_dist_between_circles)
    
    tile_map = star_map.StarMap(A, from_picture = True,
                                stars_pickle = A_pickle,
                               force_scan = force_map)

    star_map.plot_map(tile_map, "Tile Map")

    if dump:
        tile_map.dump_map("map")

def interactive_match(tile_image,
                 reference_image = None,  
                 show_images = None,
                 exp_tile_count = None,
                 exp_scale_factor = None,
                 angle_rotation_ranges = None,
                 dump_maps = None, 
                 plot_input_maps = None,
                 plot_solution_maps = None,
                 draw_matches_count = None,
                 draw_comparisons_count = None,
                 force_scan_ref = None,
                 force_scan_tile = None,
                 force_map_ref = None,
                 force_map_tile = None,  
                 unmatched_stars_weight = None,        
                 max_listed_results = None,      
                 tile_min_circle_radius = 10,
                 tile_max_circle_radius = 20, 
                 tile_gray_filter_threshold = None,
                 templ_gray_filter_threshold = None,
                 tile_min_dist_between_circles = 15,
                 paused_plot = True,
                 ):
    if reference_image is None: 
        reference_image = args.reference_image
    if show_images is None:
        show_images = args.show_debug_images
    if exp_tile_count is None:
        exp_tile_count = args.exp_ref_tile_count
    if exp_scale_factor is None:
        exp_scale_factor = args.exp_tile_scale_factor
    if angle_rotation_ranges is None:
        angle_rotation_ranges = args.rot_90deg_range
    if dump_maps is None:
        dump_maps = args.dump_maps
    if plot_input_maps is None:
        plot_input_maps = args.plot_input_maps
    if plot_solution_maps is None:
        plot_solution_maps = args.plot_solution_maps
    if draw_matches_count is None:
        draw_matches_count = args.draw_matches
    if draw_comparisons_count is None:
        draw_comparisons_count = args.draw_comparisons
    if force_scan_ref is None:
        force_scan_ref = args.force_scan_ref
    if force_scan_tile is None:
        force_scan_tile = args.force_scan_tile
    if force_map_ref is None:
        force_map_ref = args.force_map_ref
    if force_map_tile is None:
        force_map_tile = args.force_map_tile
    if unmatched_stars_weight is None:
        unmatched_stars_weight = args.unmatched_stars_weight
    if max_listed_results is None:
        max_listed_results = 10
    if tile_gray_filter_threshold is None:
        tile_gray_filter_threshold = args.tile_gray_filter_threshold
    if templ_gray_filter_threshold is None:
        templ_gray_filter_threshold = args.templ_gray_filter_threshold
    
    plt.ion() 
    
    match_images(reference_image = reference_image,
                 tile_image = tile_image,
                 show_images = show_images,
                 exp_tile_count = exp_tile_count,
                 exp_scale_factor = exp_scale_factor,
                 angle_rotation_ranges = angle_rotation_ranges,
                 dump_maps = dump_maps,
                 plot_input_maps = plot_input_maps,
                 plot_solution_maps = plot_solution_maps,
                 draw_matches_count = draw_matches_count,
                 draw_comparisons_count = draw_comparisons_count,
                 force_scan_ref = force_scan_ref,
                 force_scan_tile = force_scan_tile,
                 force_map_ref = force_map_ref,
                 force_map_tile = force_map_tile,
                 unmatched_stars_weight = unmatched_stars_weight,
                 max_listed_results = max_listed_results,
                 tile_min_circle_radius = tile_min_circle_radius,
                 tile_max_circle_radius = tile_max_circle_radius,
                 tile_gray_filter_threshold = tile_gray_filter_threshold,
                 templ_gray_filter_threshold = templ_gray_filter_threshold,
                 tile_min_dist_between_circles = tile_min_dist_between_circles,
                 paused_plot=paused_plot,
                 )

def run_interactive():
    import IPython

    IPython.embed()

if __name__ == "__main__":
    main()