#  start_map.py #

## Matching Algorithm ##

There's several parameters to the algorithm which can be adjusted to fine tune its behavior. Parameters
are shown **_like_this_** and are summarized at the bottom.

### Map Pre-Processing ###
Before doing any analysis, we need to process the two star maps at hand. We will refer to them
as __template map__ (the one with all the stars on the puzzle) and __tile map__ (the
one from a single puzzle tile/piece). Map processing involves the following actions:

1. Distance between each star pair is calculated
   a. An optimization can be made. **TODO: FILL THIS UP!**
2. Angle between each star pair is calculated

### Map Matching ###

Once distances and angles are known for all stars on the map, we proceed to match them. We will assume, one 
pair at the time, that each start on the template map matches each start on the tile map. This initial pair 
of stars will be known as ref_A stars, one on each map. **TODO: Talk about optimizations**

Then, each of the **_closest_stars_to_check_** closest stars to ref_A star on both maps is assumed to match each other.
This second pair stars is known as ref_B. A distance adjustment factor is calculated so distance within
ref_A to ref_B on tile map is the same to that distance on template map. And adjustment angle is calculated
too so angle between ref_A and ref_B stars match on both maps.

Size and angle adjustment values are applied to the star sizes, distances and angles on the tile map. **Any 
reference to the tile map from now own assumes that the start distances, sizes or angles have been adjusted
to these adjustment factors**.

We will then compare how well the tile map fits on the template map and calculate an overall score this this match.
The first check to perform is to verify the size for ref_A stars on both maps match each other.
Same for ref_B stars. The size difference between these start pairs needs to be no larger than **_max_size_diff_** %.
If any size difference exceeds that threshold then this ref_A and ref_B star match is aborted and not tested. An
overall score with value 0 is still saved to have a record of this mismatch and avoid checking this combination again.

If sizes for ref_A and ref_B stars are within tolerance, then we proceed to find a matching star on the template map
for each remaining stars on the tile map. Matching should follow the rules below.

#### Matching Rules ####

We are looking not to make new measurements on angles and distances but to use those already calculate during the 
pre-processing phase for each map. You will find some of these comparisons may not be the best way to do it but it
will make use of the existing measurements.

Matching stars should met these conditions in order to be considered a match. These measurements are taken between
ref_A star on each map and the stars being matched, also one on each map.

1. A distance error no larger than **_max_dist_diff_** % the distance of the stars on template map
2. A size error no larger than **_max_size_diff_** % the size of the star on template map
3. An _Angle distance_ error no larger than **_max_angle_dist** %
    * See the section on _Angle Distance_ below for details on this magnitude

Any star pair meeting these critetia is then graded with the scoring rules below. Otherwise the tile star score is set
to 0.

#### Scoring Rules ####

Once a match is found, we calculate the overall score. We start by calculating a score for each star on the
tile map which met the matching rules. The two reference stars (ref_A and ref_B) are also given an score.
1. An initial star score of 100 points is given for each star
2. From this star score the following vales are subtracted:
    1. For all matched stars on the tile, including ref_A and B, the size difference in percentage
      is multiplied by **_size_diff_score_factor_** and then subtracted from the star score
    2. For all matched stars on the tile, excluding ref_A and B, the distance difference (in percentage)
      is multiplied by **_dist_diff_score_factor**_ and then subtracted from the score
    3. for all matched stars on the tile, excluding ref_A and B, the Angle Distance difference
      is multiplied by **_angle_dist_score_factor_** and subtracted from the score.
3. A perfectly matched star will add 100 points to the overall score.

An **Overall Score** is then calculated for the whole match. This score is the sum of all star scores
divided by the total number of stars on the tile. A perfectly matched tile map should have a final score
of 100 points.

#### Score Information ####

For each match the following info is saved for future reference:

 * overall score points
 * scaling distance factor
 * angle adjustment
 * Index for these stars on each map
    * ref_A
    * ref_B
 * List of all the remaining stars on the tile with:
    * Index of star on tile
    * star match score. 0 if no match found.
    * Index of matching star on template map, if found.

**TODO:** 
* Consider adding a check to verify for any mismatching stars on the template map, within the area of the
matched starts to the tile tile, which are not present on the tile.
* should we add this?* A count of not matched stars, those found on the tile but not present on the 
  reference map is kept. Isn't this just any star with score 0?
* should we add this?* Search stops after **_stop_after_miss_stars_** stars from the tile are not found

#### Angle Distance ####

Comparing angles between two candidate matching stars needs some attention. Just as we stated earlier, we are
resourcing to compare already calculated parameters. Since we already have the distance and angle between each
star on both maps we decided to compare those two variables to figure out how close the two candidate stars
are from each others. However, for stars very close to each other, the angle difference is not that important
since big angle differences don't translate into large differences on the star positions. Thus, we don't want to
have big angle errors have a significant effect for stars close to each other.

We may then conclude comparing angles is not a good idea and instead we should compare the actual distance
between the tile star and the match candidate on the template map. However, calculating distances take two
square operations, one sum and one square root. If we want speed we should avoid this.

So, back to the angle difference. We stablished big angle differences over small distances should have minimal to 
no effect on the star score. However if the stars are distant to each other, we want the angle differences to
have a significant effect on the score. This is how we do that.

We asume the distance over these candidate stars to be the portion of the perimeter of a circle corresponding
to the angle error where the radius of the circle is the distance between ref_A and the matched star.
This distance is already calculated for every star and does not need to be calculated again. Any of the two maps
can be the source for this reference distance.

This is a good approximation for a small angle differences. For big angle differences this approximation
deviates and returns a distance larger than the actual value. However we don't care for it to be imprecise
as the error is big any way. Moreover, this operation only requires a multiplication and a division, less than 
the real distance calculation.

We'll use this formula to calculate the angle distance difference:
          
          angle_dist_diff = (angle_error / 360) * perimeter of a circle with same radius
                                                  as the distance within the two stars

          angle_dist_diff = (angle_error / 360) * 2 * pi * star_distance
                    where start_distance is the distance between ref_A and the match candidtate star
                    This can be from either map. We will chose the template map as the source.
       
Then, the comparisons above call for an angle distance difference in percentage. That is as follows:

          angle_dist_diff_percentage = 100 * angle_dist_diff / (distance within the two stars)

          angle_dist_diff_percentage = 100 * angle_error * (1/360) * 2 * pi * start_distance
          
          angle_dist_diff_percentage = angle_error * start_distance * K
                    where K = 100 * (1/360) * 2 * pi

## Optimizations ##

The search algorithm described above is quite compute intensive as it requires at least 6 levels of nested loops. For
a large number of stars the compute time may grow exponentially and turn into minutes or hours to map a single tile.
The process or pre-processing a large reference map may also take a long time to compute the angles and distances 
withing every star. These optimizations have been put on place to mitigate some of those issues while keeping the
algorithm fully functional and precise.

### Map Pre-processing Tile Count ###

The number of expected tiles on the template map can be passed into the algoritm as a X,Y count of tiles on the puzzle.
This number is then used to limit which stars we calculate its distance and angle against other stars. This are the
required steps.

 1. Find the max x,y coordinate for any star. Won't search for the min one as we assume the map to start on 0,0.
 2. Determine the max expected tile size on X and Y (as max_tile_x and max_tile_y)
 3. When pre-processing the template map, filter stars to calculate distance and angle for.
    If x distance > 1.2 * max_tile_x OR y distance > 1.2 * max_tile_y, skip measurements for this star pair.
 4. Calculate actual star distance. If distance > max_diagonal_tile_dist * 1.2, drop the result and don't store it

Since we are trying to avoid measuring the distance between two stars we compare only the X and Y difference as a filter.
The filter won't be precise and will let some stars outside of range seek in. However, that is better than scanning all
stars instead.