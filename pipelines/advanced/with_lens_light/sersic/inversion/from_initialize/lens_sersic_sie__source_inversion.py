import autofit as af
import autolens as al

# In this pipeline, we'll perform an initialize analysis which fits an image with a source galaxy and a lens light
# component. This reconstructs the source using a pxielized inversion, and uses the light-profile source fit of a
# previous pipeline. The pipeline is as follows:

# Phase 1:

# Description: initialize the inversion's pixelization and regularization hyper_galaxies-parameters, using a previous lens
#              light and mass model.
# Lens Light: EllipticalSersic
# Lens Mass: EllipitcalIsothermal + ExternalShear
# Source Light: VoronoiMagnification + Constant
# Previous Pipelines: initialize/lens_sie__source_sersic_from_init.py
# Prior Passing: Lens Mass (variable -> previous pipeline).
# Notes: Uses the lens subtracted image corresponding to the light model of a previous pipeline.

# Phase 2:

# Description: Refine the lens light and mass model and source inversion.
# Lens Light: EllipticalSersic
# Lens Mass: EllipitcalIsothermal + ExternalShear
# Source Light: VoronoiMagnification + Constant
# Previous Pipelines: initialize/lens_sie__source_sersic_from_init.py
# Prior Passing: Lens light and mass (variable -> previous pipeline), source inversion (variable -> phase 1).
# Notes: None

# Phase 3:

# Description: Refine the source inversion using this lens light and mass model.
# Lens Light: EllipticalSersic
# Lens Mass: EllipitcalIsothermal + ExternalShear
# Source Light: VoronoiMagnification + Constant
# Previous Pipelines: None
# Prior Passing: Lens light and mass (constant -> phase 2), source inversion (variable -> phase 1 & 2).
# Notes: Source inversion resolution varies.


def make_pipeline(
    pipeline_settings,
    phase_folders=None,
    redshift_lens=0.5,
    redshift_source=1.0,
    sub_size=2,
    signal_to_noise_limit=None,
    bin_up_factor=None,
    positions_threshold=None,
    inner_mask_radii=None,
    pixel_scale_interpolation_grid=None,
    inversion_uses_border=True,
    inversion_pixel_limit=None,
):

    ### SETUP PIPELINE AND PHASE NAMES, TAGS AND PATHS ###

    # We setup the pipeline name using the tagging module. In this case, the pipeline name is tagged according to
    # whether the lens light model is fixed throughout the pipeline.

    pipeline_name = "pipeline_inv__lens_sersic_sie__source_inversion"
    pipeline_tag = al.pipeline_tagging.pipeline_tag_from_pipeline_settings(
        include_shear=pipeline_settings.include_shear,
        fix_lens_light=pipeline_settings.fix_lens_light,
        pixelization=pipeline_settings.pixelization,
        regularization=pipeline_settings.regularization,
    )

    phase_folders.append(pipeline_name)
    phase_folders.append(pipeline_tag)

    ### PHASE 1 ###

    # In phase 1, we initialize the inversion's resolution and regularization coefficient, where we:

    # 1) Use a lens-subtracted image generated by subtracting model lens galaxy image from phase 3 of the initialize
    #    pipeline.
    # 2) Fix our mass model to the lens galaxy mass-model from phase 3 of the initialize pipeline.
    # 3) Use a circular mask which includes all of the source-galaxy light.

    phase1 = al.PhaseImaging(
        phase_name="phase_1__source_inversion_initialization",
        phase_folders=phase_folders,
        galaxies=dict(
            lens=al.GalaxyModel(
                redshift=redshift_lens,
                light=af.last.instance.galaxies.lens.light,
                mass=af.last.instance.galaxies.lens.mass,
                shear=af.last.instance.galaxies.lens.shear,
            ),
            source=al.GalaxyModel(
                redshift=redshift_source,
                pixelization=pipeline_settings.pixelization,
                regularization=pipeline_settings.regularization,
            ),
        ),
        sub_size=sub_size,
        signal_to_noise_limit=signal_to_noise_limit,
        bin_up_factor=bin_up_factor,
        positions_threshold=positions_threshold,
        inner_mask_radii=inner_mask_radii,
        pixel_scale_interpolation_grid=pixel_scale_interpolation_grid,
        inversion_uses_border=inversion_uses_border,
        inversion_pixel_limit=inversion_pixel_limit,
        optimizer_class=af.MultiNest,
    )

    phase1.optimizer.const_efficiency_mode = True
    phase1.optimizer.n_live_points = 20
    phase1.optimizer.sampling_efficiency = 0.8

    ### PHASE 2 ###

    # In phase 2, we fit the len galaxy light, mass and source galaxy simultaneously, using an inversion. We will:

    # 1) Initialize the priors of the lens galaxy and source galaxy from phase 3 of the previous pipeline and phase 1
    #    of this pipeline.
    # 2) Use a circular mask including both the lens and source galaxy light.

    lens = al.GalaxyModel(
            redshift=redshift_lens,
            bulge=af.last.model.galaxies.lens.bulge,
            disk=af.last.model.galaxies.lens.disk,
            mass=af.last.model.galaxies.lens.mass,
            shear=af.last.model.galaxies.lens.shear,
        )

    # If the lens light is fixed, over-write the pass prior above to fix the lens light model.

    if pipeline_settings.fix_lens_light:

        lens.light = af.last.instance.galaxies.lens.light

    phase2 = al.PhaseImaging(
        phase_name="phase_2__lens_sersic_sie__source_inversion",
        phase_folders=phase_folders,
        galaxies=dict(
            lens=lens,
            source=al.GalaxyModel(
                redshift=redshift_source,
                pixelization=phase1.result.instance.galaxies.source.pixelization,
                regularization=phase1.result.instance.galaxies.source.regularization,
            ),
        ),
        sub_size=sub_size,
        signal_to_noise_limit=signal_to_noise_limit,
        bin_up_factor=bin_up_factor,
        positions_threshold=positions_threshold,
        inner_mask_radii=inner_mask_radii,
        pixel_scale_interpolation_grid=pixel_scale_interpolation_grid,
        inversion_uses_border=inversion_uses_border,
        inversion_pixel_limit=inversion_pixel_limit,
        optimizer_class=af.MultiNest,
    )

    phase2.optimizer.const_efficiency_mode = True
    phase2.optimizer.n_live_points = 75
    phase2.optimizer.sampling_efficiency = 0.2

    phase2 = phase2.extend_with_inversion_phase()

    return al.PipelineDataset(pipeline_name, phase1, phase2)
