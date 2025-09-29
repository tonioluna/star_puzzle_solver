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

import numpy as np
from scipy.spatial.distance import cdist
from scipy.optimize import linear_sum_assignment

def find_stars(image_path, 
               gray_filter_threshold = 64,
               adaptive_block_size = 49,
               adaptive_sub_constant = 0,
               show_images = False,
               bad_circle_filter_threshold = 128,
               bad_circle_filter_no_check = 8,
               min_dist_between_circles = 5,
               min_circle_radius = 2,
               max_circle_radius = 20,
               force_scan = False,
               ):
    
    if show_images:
        force_scan = True

    pickle_name = f"{os.path.basename(image_path)}."  \
                  f"gft_{gray_filter_threshold}."   \
                  f"abz_{adaptive_block_size}."   \
                  f"asc_{gray_filter_threshold}."   \
                  f"bcft_{gray_filter_threshold}."   \
                  f"bcfnc_{gray_filter_threshold}."   \
                  f"mdbc_{gray_filter_threshold}."   \
                  f"mncr_{gray_filter_threshold}."   \
                  f"mxcr_{gray_filter_threshold}.pkl"
    
    _log.info("Getting stars from %s"%(image_path,))
    if os.path.exists(pickle_name) and not force_scan:
        _log.info("Pickle exists, loading: %s"%(pickle_name,))
        with open(pickle_name, "rb") as fh:
            return pickle.load(fh)

    _log.info("Piclke does not exist, scanning image...")
    stars = scan_stars(image_path = image_path, 
                       gray_filter_threshold = gray_filter_threshold,
                       adaptive_block_size = adaptive_block_size,
                       adaptive_sub_constant = adaptive_sub_constant,
                       show_images = show_images,
                       bad_circle_filter_threshold = bad_circle_filter_threshold,
                       bad_circle_filter_no_check = bad_circle_filter_no_check,
                       min_dist_between_circles = min_dist_between_circles,
                       min_circle_radius = min_circle_radius,
                       max_circle_radius = max_circle_radius,
                       )
    
    _log.info("Saving stars to pickle: %s"%(pickle_name,))
    with open(pickle_name, "wb") as fh:
        pickle.dump(stars, fh)
    
    return stars

def scan_stars(image_path, 
               gray_filter_threshold = 64,
               adaptive_block_size = 49,
               adaptive_sub_constant = 0,
               show_images = False,
               bad_circle_filter_threshold = 128,
               bad_circle_filter_no_check = 8,
               min_dist_between_circles = 5,
               min_circle_radius = 4,
               max_circle_radius = 20,
               ):

    _log.info("Loading image...")
    image = cv2.imread(image_path)
    _log.info("  \\--> Done!")
    
    _log.info("Loading image...")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _log.info("  \\--> Done!")
    
    gray_filtered = gray.copy()
    if gray_filter_threshold is not None:
        _log.info("Applying gray threshold filter... TODO: find a better way to do this?")
        for row in range(len(gray_filtered)):
            for col in range(len(gray_filtered[row])):
                #if gray[row][col] < 64:
                #    gray[row][col] = 0
                gray_filtered[row][col] = max(0, int(gray_filtered[row][col]) - gray_filter_threshold)
        _log.info("  \\--> Done!")

    _log.info("Applying adaptive threshold filter...")
    thresh = cv2.adaptiveThreshold(
        gray_filtered,                # input image (grayscale)
        255,                # maximum value to assign
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # thresholding method
        cv2.THRESH_BINARY,  # type of thresholding
        adaptive_block_size,                 # block size (size of neighborhood to calculate threshold)
        adaptive_sub_constant                   # constant subtracted from the mean/weighted sum
    )
    _log.info("  \\--> Done!")

    _log.info("Finding circles...")
    #circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1, 5, param1=10, param2=25, minRadius=2, maxRadius=20)
    circles = cv2.HoughCircles(image = thresh, 
                               method = cv2.HOUGH_GRADIENT, 
                               dp = 1, 
                               minDist = min_dist_between_circles, 
                               param1=9, 
                               param2=9, 
                               minRadius=min_circle_radius, 
                               maxRadius=max_circle_radius)
    circles = np.uint16(np.around(circles))[0]
    _log.info("  \\--> Done!")

    if circles is None:
        raise Exception("Did not find any circle!")

    _log.info("Filtering empty circles...")

    good_circles = []
    bad_circles = []

    for (x, y, r) in circles:
        # circles under certain size are assumed to be always correct, shouldn't be false detections
        if r <= bad_circle_filter_no_check:
            good_circles.append((x,y,r))
            continue

        # create masks
        mask = np.zeros_like(thresh)
        cv2.circle(mask, (x, y), r, 255, -1)  # inside

        mean_ring = cv2.mean(thresh, mask=mask)[0]

        if mean_ring > bad_circle_filter_threshold:  # tweak threshold
            good_circles.append((x,y,r))
        else:
            bad_circles.append((x,y,r))
    
    # Make star map

    if show_images:    
        _log.info("Found %i good circles and %i false/empty circles"%(len(good_circles), len(bad_circles)))
        img_good_circles = image.copy()
        img_bad_circles = image.copy()
        for i in good_circles:
            # Draw the outer circle
            cv2.circle(img_good_circles, (i[0], i[1]), i[2], (0, 255, 0), 2)
            # Draw the center of the circle
            cv2.circle(img_good_circles, (i[0], i[1]), 2, (255, 0, 0), 3)
        for i in bad_circles:
            # Draw the outer circle
            cv2.circle(img_bad_circles, (i[0], i[1]), i[2], (0, 255, 0), 2)
            # Draw the center of the circle
            cv2.circle(img_bad_circles, (i[0], i[1]), 2, (255, 0, 0), 3)
                

        #plt.imshow(image)
        #plt.show()

        fig, axes = plt.subplots(2, 3)

        # Display the first image in the first subplot
        #axes[0].imshow(blurred)
        #axes[0].set_title('blurred')
        #axes[0].axis('off') # Turn off axis labels and ticks

        axes[0][0].imshow(image)
        axes[0][0].set_title('Original')
        axes[0][0].axis('off') # Turn off axis labels and ticks

        # Display the second image in the second subplot
        axes[0][1].imshow(gray)
        axes[0][1].set_title('gray')
        axes[0][1].axis('off') # Turn off axis labels and ticks

        # Display the second image in the second subplot
        axes[0][2].imshow(gray_filtered)
        axes[0][2].set_title('gray filtered')
        axes[0][2].axis('off') # Turn off axis labels and ticks

        axes[1][0].imshow(thresh)
        axes[1][0].set_title('thresh')
        axes[1][0].axis('off') # Turn off axis labels and ticks

        # Display the second image in the second subplot
        axes[1][1].imshow(img_good_circles)
        axes[1][1].set_title('circles')
        axes[1][1].axis('off') # Turn off axis labels and ticks

        axes[1][2].imshow(img_bad_circles)
        axes[1][2].set_title('bad circles')
        axes[1][2].axis('off') # Turn off axis labels and ticks

        # Adjust layout to prevent titles from overlapping
        plt.tight_layout()

        # Show the plot with both images
        plt.show(block = False)
    
    return good_circles

def draw_matches(image_path, 
                 ref_map,
                 scores
                ):

    _log.info("Loading image...")
    image = cv2.imread(image_path)
    _log.info("  \\--> Done!")
    
    stars = []
    for score in scores:
        stars.extend([r for t,r in score._mappings.items() if r is not None])
    stars = list(set(stars))

    for s in stars:
        i = ref_map._stars[s]
        
        if ref_map.from_pic_y_correction is not None:
            i = list(i)
            i[1] = ref_map.from_pic_y_correction - i[1]

        i = [int(x) for x in i]
        # Draw the outer circle
        cv2.circle(image, (i[0], i[1]), i[2], (0, 255, 0), 2)
        # Draw the center of the circle
        cv2.circle(image, (i[0], i[1]), 2, (255, 0, 0), 3)
        
    plt.imshow(image)

def match_images(reference_image, 
                 tile_image,
                 show_images = False,
                 exp_tile_count = None,
                 exp_scale_factor = None,
                 angle_rotation_ranges = None):
    A = np.array(find_stars(reference_image,
                           show_images=show_images), dtype=float)
    B = np.array(find_stars(tile_image,
                            show_images=show_images,
                            gray_filter_threshold = 120), dtype=float)

    _log.info("Ref image has %i stars"%(len(A),))
    _log.info("Tile image has %i stars"%(len(B),))

    ref_map = star_map.StarMap(A, from_picture = True,
                               exp_tile_count = exp_tile_count)
    tile_map = star_map.StarMap(B, from_picture = True)

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
                     scores[:5])
    

def main():
    global _log

    parser = argparse.ArgumentParser(description="Mock mode checker options")
    parser.add_argument("-L", "--logfile",          dest="logfile",                 default=None, help="Path to log file")
    parser.add_argument("--reference_image",        dest="reference_image",         default=None, help="ID for the map to use as reference")
    parser.add_argument("--tile_image",             dest="tile_image",              default=None, help="ID for the map to use as tile")
    parser.add_argument("--exp_ref_tile_count",     dest="exp_ref_tile_count",      default=None,                         type=star_map.arg_x_y_count,    help="Expected count of X and Y tiles/puzzle pieces on the template/reference map. Default: %(default)s%%")
    parser.add_argument("--exp_tile_scale_factor",  dest="exp_tile_scale_factor",   default=None,                         type=star_map.arg_scale_factor, help="Expected scale factor range for the provided tile. Default: %(default)s%%")
    parser.add_argument("--rot_90deg_range",        dest="rot_90deg_range",         default=None,                         type=star_map.arg_rot_90deg_range, help="Limit the max deviation from 90 degrees the tile can have. Default: %(default)s")
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
    _log.info("Logger name: %s"%(args.logfile,))


    match_images(args.reference_image, 
                 args.tile_image,
                 show_images=True,
                 exp_tile_count = args.exp_ref_tile_count,
                 exp_scale_factor = args.exp_tile_scale_factor,
                 angle_rotation_ranges = args.rot_90deg_range)
    #match_images("reference_0.jpg", "fake_tile_1.jpg", show_images=True)
    input("Hit ENTER to exit!")

if __name__ == "__main__":
    main()