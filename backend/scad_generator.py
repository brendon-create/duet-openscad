def generate_scad_script(letter1, letter2, font1, font2, size, pendant_x, pendant_y, pendant_z, pendant_rotation_y):
    if size <= 20:
        fn = 64
    elif size <= 25:
        fn = 56
    else:
        fn = 48
    
    depth = size * 5.0
    
    scad_script = f'''$fn = {fn};

letter1 = "{letter1}";
letter2 = "{letter2}";
font1 = "{font1}";
font2 = "{font2}";
target_height = {size};
depth = {depth};
pendant_x = {pendant_x};
pendant_y = {pendant_y};
pendant_z = {pendant_z};
pendant_rotation = {pendant_rotation_y};
pendant_outer_d = target_height * 0.15 * 2;
pendant_tube_d = target_height * 0.03 * 2;

module letter1_shape() {{
    rotate([90, 0, 0])
        linear_extrude(height = depth, center = true)
            text(letter1, size = target_height, font = font1, halign = "center", valign = "center");
}}

module letter2_shape() {{
    rotate([0, 90, 0])
        linear_extrude(height = depth, center = true)
            text(letter2, size = target_height, font = font2, halign = "center", valign = "center");
}}

module pendant() {{
    rotate([0, 90, 0])
        rotate_extrude($fn = 32)
            translate([pendant_outer_d / 2, 0, 0])
                circle(d = pendant_tube_d, $fn = 24);
}}

intersection() {{
    letter1_shape();
    letter2_shape();
}}

translate([pendant_x, pendant_y, target_height / 2 + pendant_outer_d / 2 + pendant_z])
    rotate([0, 0, pendant_rotation])
        pendant();
'''
    return scad_script
