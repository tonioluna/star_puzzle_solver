import sys
import pickle
import os
import cv2
from matplotlib import pyplot as plt
import numpy as np

import numpy as np
from scipy.spatial.distance import cdist
from scipy.optimize import linear_sum_assignment

# -------------------------
# Step 1: Build signatures
# -------------------------
def build_signature(points, k=None):
    coords = points[:, :2]
    radii = points[:, 2]
    dist_matrix = cdist(coords, coords)
    np.fill_diagonal(dist_matrix, np.inf)
    
    signatures = []
    for i in range(len(points)):
        dists = np.sort(dist_matrix[i])
        if k is not None:
            dists = dists[:k]
        sig = np.concatenate([dists, [radii[i]]])
        signatures.append(sig)
    return signatures


# -------------------------
# Step 2: Candidate matching
# -------------------------
def candidate_matching(A, B, k=5, max_cost=5.0):
    sigA = build_signature(A, k=k)
    sigB = build_signature(B, k=k)

    cost = np.zeros((len(sigA), len(sigB)))
    for i, sA in enumerate(sigA):
        for j, sB in enumerate(sigB):
            m = min(len(sA), len(sB))
            cost[i, j] = np.linalg.norm(sA[:m] - sB[:m])

    row_ind, col_ind = linear_sum_assignment(cost)

    matches = []
    for i, j in zip(row_ind, col_ind):
        if cost[i, j] < max_cost:
            matches.append((i, j, cost[i, j]))
    return matches


# -------------------------
# Step 3: Similarity transform (rotation + translation + scale)
# -------------------------
def estimate_similarity_transform(A_coords, B_coords):
    """
    Compute scale, rotation (2x2), and translation (2,)
    such that B aligns with A.
    """
    centroid_A = np.mean(A_coords, axis=0)
    centroid_B = np.mean(B_coords, axis=0)

    AA = A_coords - centroid_A
    BB = B_coords - centroid_B

    # SVD for rotation
    H = BB.T @ AA
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[1, :] *= -1
        R = Vt.T @ U.T

    # Scale factor
    var_B = np.sum(np.square(BB))
    s = np.trace((BB @ R).T @ AA) / var_B

    # Translation
    t = centroid_A - s * (R @ centroid_B)

    return s, R, t


def apply_similarity_transform(points, s, R, t):
    coords = points[:, :2]
    transformed = (s * (coords @ R.T)) + t
    return np.hstack([transformed, points[:, 2:3]])


def refine_with_consistency(A, B_aligned, tol=3.0, min_fraction=0.6):
    """
    Check if alignment explains most points.
    Returns final matches if consistent, else [].
    """
    dist = cdist(A[:, :2], B_aligned[:, :2])

    # Hungarian for best assignment
    row_ind, col_ind = linear_sum_assignment(dist)
    matches = [(i, j, dist[i, j]) for i, j in zip(row_ind, col_ind) if dist[i, j] < tol]

    # Fraction of explained points (coverage)
    coverage_A = len({i for i, _, _ in matches}) / len(A)
    coverage_B = len({j for _, j, _ in matches}) / len(B_aligned)
    coverage = min(coverage_A, coverage_B)

    if coverage >= min_fraction:
        return matches
    else:
        return []  # reject false positive

# -------------------------
# Step 4: Full pipeline
# -------------------------
def match_point_sets(A, B, k=5, max_cost=5.0, refine=True):
    # Step 1-2: Candidate matches
    matches = candidate_matching(A, B, k=k, max_cost=max_cost)
    if len(matches) < 2:
        return []

    # Extract matched coordinates
    A_coords = np.array([A[i, :2] for i, _, _ in matches])
    B_coords = np.array([B[j, :2] for _, j, _ in matches])

    # Step 3: Estimate similarity transform
    s, R, t = estimate_similarity_transform(A_coords, B_coords)
    # Force positive scale
    if s < 0:
        s = -s
        R = -R

    # Option B, does not seem to work so good
    #  # Step 4: Refinement
    #  if refine:
    #      B_aligned = apply_similarity_transform(B, s, R, t)
    #      matches = refine_with_consistency(A, B_aligned, tol=3.0, min_fraction=0.6)
    #      #dist = cdist(A[:, :2], B_aligned[:, :2])
    #      #row_ind, col_ind = linear_sum_assignment(dist)
    #      #refined = []
    #      #for i, j in zip(row_ind, col_ind):
    #      #    if dist[i, j] < max_cost:
    #      #        refined.append((i, j, dist[i, j]))
    #      #return refined, (s, R, t)


    # Step 4: Refinement
    if refine:
        B_aligned = apply_similarity_transform(B, s, R, t)
        dist = cdist(A[:, :2], B_aligned[:, :2])
        row_ind, col_ind = linear_sum_assignment(dist)
        refined = []
        for i, j in zip(row_ind, col_ind):
            if dist[i, j] < max_cost:
                refined.append((i, j, dist[i, j]))
        return refined, (s, R, t)

    return matches, (s, R, t)

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
    
    print("Getting stars from %s"%(image_path,))
    if os.path.exists(pickle_name) and not force_scan:
        print("Pickle exists, loading: %s"%(pickle_name,))
        with open(pickle_name, "rb") as fh:
            return pickle.load(fh)

    print("Piclke does not exist, scanning image...")
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
    
    print("Saving stars to pickle: %s"%(pickle_name,))
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

    print("Loading image...")
    image = cv2.imread(image_path)
    print("  \\--> Done!")
    
    print("Loading image...")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    print("  \\--> Done!")
    
    gray_filtered = gray.copy()
    if gray_filter_threshold is not None:
        print("Applying gray threshold filter... TODO: find a better way to do this?")
        for row in range(len(gray_filtered)):
            for col in range(len(gray_filtered[row])):
                #if gray[row][col] < 64:
                #    gray[row][col] = 0
                gray_filtered[row][col] = max(0, int(gray_filtered[row][col]) - gray_filter_threshold)
        print("  \\--> Done!")

    print("Applying adaptive threshold filter...")
    thresh = cv2.adaptiveThreshold(
        gray_filtered,                # input image (grayscale)
        255,                # maximum value to assign
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # thresholding method
        cv2.THRESH_BINARY,  # type of thresholding
        adaptive_block_size,                 # block size (size of neighborhood to calculate threshold)
        adaptive_sub_constant                   # constant subtracted from the mean/weighted sum
    )
    print("  \\--> Done!")

    print("Finding circles...")
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
    print("  \\--> Done!")

    if circles is None:
        raise Exception("Did not find any circle!")

    print("Filtering empty circles...")

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
        print("Found %i good circles and %i false/empty circles"%(len(good_circles), len(bad_circles)))
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

def draw_matches(ref_img, tile_img, match_ref_stars, match_tile_stars):
    ref_with_match = cv2.imread(ref_img)
    tile_with_match = cv2.imread(tile_img)

    for i in match_ref_stars:
        # Draw the outer circle
        cv2.circle(ref_with_match, (i[0], i[1]), i[2], (0, 255, 0), 2)
        # Draw the center of the circle
        cv2.circle(ref_with_match, (i[0], i[1]), 2, (255, 0, 0), 3)
    for i in match_tile_stars:
        # Draw the outer circle
        cv2.circle(tile_with_match, (i[0], i[1]), i[2], (0, 255, 0), 2)
        # Draw the center of the circle
        cv2.circle(tile_with_match, (i[0], i[1]), 2, (255, 0, 0), 3)
                

    #plt.imshow(image)
    #plt.show()

    fig, axes = plt.subplots(1, 2)

    # Display the first image in the first subplot
    #axes[0].imshow(blurred)
    #axes[0].set_title('blurred')
    #axes[0].axis('off') # Turn off axis labels and ticks

    axes[0].imshow(ref_with_match)
    axes[0].set_title('Original')
    axes[0].axis('off') # Turn off axis labels and ticks

    # Display the second image in the second subplot
    axes[1].imshow(tile_with_match)
    axes[1].set_title('gray')
    axes[1].axis('off') # Turn off axis labels and ticks

    # Adjust layout to prevent titles from overlapping
    plt.tight_layout()

    # Show the plot with both images
    plt.show(block = False)

def match_images(reference_image, 
                 tile_image,
                 show_images = False):
    A = np.array(find_stars(reference_image,
                           show_images=show_images))#, dtype=float)
    B = np.array(find_stars(tile_image,
                            show_images=show_images,
                            gray_filter_threshold = 120))#, dtype=float)

    print("Ref image has %i stars"%(len(A),))
    print("Tile image has %i stars"%(len(B),))

    #A = np.array([[0,0,1], [10,0,1], [0,10,1], [10,10,2], [5,5,1.5]])

    # Generate B with scale, rotation, translation
    theta = np.deg2rad(20)
    R_true = np.array([[np.cos(theta), -np.sin(theta)],
                       [np.sin(theta),  np.cos(theta)]])
    s_true = 1.3
    t_true = np.array([4, -3])

    #B = np.array([[0,0,1], [10,0,1], [0,10,1], [10,10,2]])  # missing center
    B[:, :2] = (s_true * (B[:, :2] @ R_true.T)) + t_true
    #B[:, 2] += np.random.normal(0, 0.1, size=len(B))

    matches, (s_est, R_est, t_est) = match_point_sets(A, B, k=3, max_cost=2000.0)

    matched_ref_stars = []
    matched_tile_stars = []

    print("Matches (A idx → B idx):")
    for i, j, d in matches:
        print(f"A[{i}] ↔ B[{j}]  (dist {d:.2f})")
        matched_ref_stars.append(A[i])
        matched_tile_stars.append(B[j])

    print("\nEstimated scale:", s_est)
    print("Estimated rotation:\n", R_est)
    print("Estimated translation:", t_est)

    draw_matches(ref_img = reference_image,
                 tile_img = tile_image, 
                 match_ref_stars = matched_ref_stars, 
                 match_tile_stars = matched_tile_stars)

match_images("reference_0.jpg", "tile_0.jpg", show_images=True)
#match_images("reference_0.jpg", "fake_tile_1.jpg", show_images=True)
input()