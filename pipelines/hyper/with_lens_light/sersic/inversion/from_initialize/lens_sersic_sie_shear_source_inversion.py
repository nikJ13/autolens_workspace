import autofit as af
from autolens.model.galaxy import galaxy_model as gm
from autolens.pipeline.phase import phase_imaging, phase_extensions
from autolens.pipeline import pipeline
from autolens.pipeline import tagging as tag
from autolens.model.profiles import light_profiles as lp
from autolens.model.profiles import mass_profiles as mp
from autolens.model.inversion import pixelizations as pix
from autolens.model.inversion import regularization as reg

# In this pipeline, we'll perform an inversion analysis which fits an image with a source galaxy and a lens light
# component.
#
# This first reconstructs the source using a magnification based pxielized inversion, initialized using the
# light-profile source fit of a previous pipeline. This ensures that the hyper-image used by the pl_pixelization and
# pl_regularization is fitted using a pixelized source-plane, which ensures that irregular structure in the lensed
# source is adapted too.

# The pipeline is as follows:

# Phase 1:

# Description: initialize the inversion's pixelization and regularization, using a magnification based pixel-grid and
#              the previous lens mass model.
# Lens Light: EllipticalSersic
# Lens Mass: EllipitcalIsothermal + ExternalShear
# Source Light: VoronoiBrightnessImage + Constant
# Previous Pipelines: initialize/lens_sie_shear_source_sersic_from_init.py
# Prior Passing: Lens Mass (variable -> previous pipeline).
# Notes: Uses the lens subtracted image corresponding to the light model of a previous pipeline.

# Phase 2:

# Description: Refine the lens light and mass model using the source inversion.
# Lens Light: EllipticalSersic
# Lens Mass: EllipitcalIsothermal + ExternalShear
# Source Light: VoronoiBrightnessImage + Constant
# Previous Pipelines: initialize/lens_sie_shear_source_sersic_from_init.py
# Prior Passing: Lens light and mass (variable -> previous pipeline), source inversion (variable -> phase 1).
# Notes: None

# Phase 3:

# Description: initialize the inversion's pixelization and regularization, using the input hyper-pixelization,
#              hyper-regularization and the previous lens mass model.
# Lens Light: EllipticalSersic
# Lens Mass: EllipitcalIsothermal + ExternalShear
# Source Light: VoronoiBrightnessImage + Constant
# Previous Pipelines: None
# Prior Passing: Lens light and mass (constant -> phase 2), source inversion (variable -> phase 1 & 2).
# Notes: Source inversion resolution varies.

# Phase 4:

# Description: Refine the lens mass model using the hyper-inversion.
# Lens Light: EllipticalSersic
# Lens Mass: EllipitcalIsothermal + ExternalShear
# Source Light: pl_pixelization + pl_regularization
# Previous Pipelines: initialize/lens_sie_shear_source_sersic_from_init.py
# Prior Passing: Lens Mass (variable -> previous pipeline), source inversion (variable -> phase 1).
# Notes: Source inversion is fixed.


def make_pipeline(
    pl_fix_lens_light=False,
    pl_hyper_galaxies=True,
    pl_hyper_background_sky=True,
    pl_hyper_background_noise=True,
    pl_pixelization=pix.VoronoiBrightnessImage,
    pl_regularization=reg.AdaptiveBrightness,
    phase_folders=None,
    tag_phases=True,
    redshift_lens=0.5,
    redshift_source=1.0,
    sub_grid_size=2,
    bin_up_factor=None,
    positions_threshold=None,
    inner_mask_radii=None,
    interp_pixel_scale=None,
    inversion_pixel_limit=None,
    cluster_pixel_scale=0.1,
):

    ### SETUP PIPELINE AND PHASE NAMES, TAGS AND PATHS ###

    # We setup the pipeline name using the tagging module. In this case, the pipeline name is tagged according to
    # whether the lens light model is fixed throughout the pipeline.

    pipeline_name = "pipeline_inv__lens_sersic_sie_shear_source_inversion"

    pipeline_name = tag.pipeline_name_from_name_and_settings(
        pipeline_name=pipeline_name,
        fix_lens_light=pl_fix_lens_light,
        pixelization=pl_pixelization,
        regularization=pl_regularization,
    )

    phase_folders.append(pipeline_name)

    ### PHASE 1 ###

    # In phase 1, we initialize the inversion's resolution and regularization coefficient, where we:

    # 1) Use a lens-subtracted image generated by subtracting model lens galaxy image from phase 3 of the initialize
    #    pipeline.
    # 2) Fix our mass model to the lens galaxy mass-model from phase 3 of the initialize pipeline.
    # 3) Use a circular mask which includes all of the source-galaxy light.

    class InversionPhase(phase_imaging.LensSourcePlanePhase):
        def pass_priors(self, results):

            ## Lens Light & Mass, Sersic -> Sersic, SIE -> SIE, Shear -> Shear ###

            self.lens_galaxies.lens = results.from_phase(
                "phase_3_lens_sersic_sie_shear_source_sersic"
            ).constant.lens_galaxies.lens

            ## Set all hyper-galaxies if feature is turned on ##

            if pl_hyper_galaxies:

                self.lens_galaxies.lens.hyper_galaxy = (
                    results.last.hyper_combined.constant.lens_galaxies.lens.hyper_galaxy
                )

            if pl_hyper_background_sky:

                self.hyper_image_sky = (
                    results.last.hyper_combined.constant.hyper_image_sky
                )

            if pl_hyper_background_noise:

                self.hyper_noise_background = (
                    results.last.hyper_combined.constant.hyper_noise_background
                )

    phase1 = InversionPhase(
        phase_name="phase_1_initialize_magnification_inversion",
        phase_folders=phase_folders,
        tag_phases=tag_phases,
        lens_galaxies=dict(
            lens=gm.GalaxyModel(
                redshift=redshift_lens,
                light=lp.EllipticalSersic,
                mass=mp.EllipticalIsothermal,
                shear=mp.ExternalShear,
            )
        ),
        source_galaxies=dict(
            source=gm.GalaxyModel(
                redshift=redshift_source,
                pixelization=pix.VoronoiMagnification,
                regularization=reg.Constant,
            )
        ),
        sub_grid_size=sub_grid_size,
        bin_up_factor=bin_up_factor,
        positions_threshold=positions_threshold,
        inner_mask_radii=inner_mask_radii,
        interp_pixel_scale=interp_pixel_scale,
        inversion_pixel_limit=inversion_pixel_limit,
        cluster_pixel_scale=cluster_pixel_scale,
        optimizer_class=af.MultiNest,
    )

    phase1.optimizer.const_efficiency_mode = True
    phase1.optimizer.n_live_points = 20
    phase1.optimizer.sampling_efficiency = 0.8

    phase1 = phase1.extend_with_multiple_hyper_phases(
        hyper_galaxy=pl_hyper_galaxies,
        include_background_sky=pl_hyper_background_sky,
        include_background_noise=pl_hyper_background_noise,
        inversion=False,
    )

    ### PHASE 2 ###

    # In phase 2, we fit the len galaxy light, mass and source galaxy simultaneously, using an inversion. We will:

    # 1) Initialize the priors of the lens galaxy and source galaxy from phase 3 of the previous pipeline and phase 1
    #    of this pipeline.
    # 2) Use a circular mask including both the lens and source galaxy light.

    class InversionPhase(phase_imaging.LensSourcePlanePhase):
        def pass_priors(self, results):

            ## Lens Light & Mass, Sersic -> Sersic, SIE -> SIE, Shear -> Shear ###

            self.lens_galaxies.lens = results.from_phase(
                "phase_3_lens_sersic_sie_shear_source_sersic"
            ).variable.lens_galaxies.lens

            # If the lens light is fixed, over-write the pass prior above to fix the lens light model.

            if pl_fix_lens_light:

                self.lens_galaxies.lens.light = results.from_phase(
                    "phase_3_lens_sersic_sie_shear_source_sersic"
                ).constant.lens_galaxies.lens.light

            ### Source Inversion, Inv -> Inv ###

            self.source_galaxies.source = results.from_phase(
                "phase_1_initialize_magnification_inversion"
            ).constant.source_galaxies.source

            ## Set all hyper-galaxies if feature is turned on ##

            if pl_hyper_galaxies:

                self.lens_galaxies.lens.hyper_galaxy = (
                    results.last.hyper_combined.constant.lens_galaxies.lens.hyper_galaxy
                )

            if pl_hyper_background_sky:

                self.hyper_image_sky = (
                    results.last.hyper_combined.constant.hyper_image_sky
                )

            if pl_hyper_background_noise:

                self.hyper_noise_background = (
                    results.last.hyper_combined.constant.hyper_noise_background
                )

    phase2 = InversionPhase(
        phase_name="phase_2_lens_sersic_sie_shear_source_magnification_inversion",
        phase_folders=phase_folders,
        tag_phases=tag_phases,
        lens_galaxies=dict(
            lens=gm.GalaxyModel(
                redshift=redshift_lens,
                light=lp.EllipticalSersic,
                mass=mp.EllipticalIsothermal,
                shear=mp.ExternalShear,
            )
        ),
        source_galaxies=dict(
            source=gm.GalaxyModel(
                redshift=redshift_source,
                pixelization=pl_pixelization,
                regularization=pl_regularization,
            )
        ),
        sub_grid_size=sub_grid_size,
        bin_up_factor=bin_up_factor,
        positions_threshold=positions_threshold,
        inner_mask_radii=inner_mask_radii,
        interp_pixel_scale=interp_pixel_scale,
        inversion_pixel_limit=inversion_pixel_limit,
        cluster_pixel_scale=cluster_pixel_scale,
        optimizer_class=af.MultiNest,
    )

    phase2.optimizer.const_efficiency_mode = True
    phase2.optimizer.n_live_points = 75
    phase2.optimizer.sampling_efficiency = 0.2

    phase2 = phase2.extend_with_multiple_hyper_phases(
        hyper_galaxy=pl_hyper_galaxies,
        include_background_sky=pl_hyper_background_sky,
        include_background_noise=pl_hyper_background_noise,
        inversion=False,
    )

    ### PHASE 3 ###

    # In phase 3, we initialize the inversion's resolution and regularization coefficient, where we:

    # 1) Use a lens-subtracted image generated by subtracting model lens galaxy image from phase 3 of the initialize
    #    pipeline.
    # 2) Fix our mass model to the lens galaxy mass-model from phase 3 of the initialize pipeline.
    # 3) Use a circular mask which includes all of the source-galaxy light.

    class InversionPhase(phase_imaging.LensSourcePlanePhase):
        def pass_priors(self, results):

            ## Lens Light & Mass, Sersic -> Sersic, SIE -> SIE, Shear -> Shear ###

            self.lens_galaxies.lens = results.from_phase(
                "phase_2_lens_sersic_sie_shear_source_magnification_inversion"
            ).constant.lens_galaxies.lens

            ## Set all hyper-galaxies if feature is turned on ##

            if pl_hyper_galaxies:

                self.lens_galaxies.lens.hyper_galaxy = (
                    results.last.hyper_combined.constant.lens_galaxies.lens.hyper_galaxy
                )

            if pl_hyper_background_sky:

                self.hyper_image_sky = (
                    results.last.hyper_combined.constant.hyper_image_sky
                )

            if pl_hyper_background_noise:

                self.hyper_noise_background = (
                    results.last.hyper_combined.constant.hyper_noise_background
                )

    phase3 = InversionPhase(
        phase_name="phase_3_initialize_inversion",
        phase_folders=phase_folders,
        tag_phases=tag_phases,
        lens_galaxies=dict(
            lens=gm.GalaxyModel(
                redshift=redshift_lens,
                light=lp.EllipticalSersic,
                mass=mp.EllipticalIsothermal,
                shear=mp.ExternalShear,
            )
        ),
        source_galaxies=dict(
            source=gm.GalaxyModel(
                redshift=redshift_source,
                pixelization=pl_pixelization,
                regularization=pl_regularization,
            )
        ),
        sub_grid_size=sub_grid_size,
        bin_up_factor=bin_up_factor,
        positions_threshold=positions_threshold,
        inner_mask_radii=inner_mask_radii,
        interp_pixel_scale=interp_pixel_scale,
        inversion_pixel_limit=inversion_pixel_limit,
        cluster_pixel_scale=cluster_pixel_scale,
        optimizer_class=af.MultiNest,
    )

    phase3.optimizer.const_efficiency_mode = True
    phase3.optimizer.n_live_points = 20
    phase3.optimizer.sampling_efficiency = 0.8

    phase3 = phase3.extend_with_multiple_hyper_phases(
        hyper_galaxy=pl_hyper_galaxies,
        include_background_sky=pl_hyper_background_sky,
        include_background_noise=pl_hyper_background_noise,
        inversion=True,
    )

    ### PHASE 4 ###

    # In phase 4, we fit the len galaxy light, mass and source galaxy simultaneously, using an inversion. We will:

    # 1) Initialize the priors of the lens galaxy and source galaxy from phase 2.
    # 2) Use a circular mask including both the lens and source galaxy light.

    class InversionPhase(phase_imaging.LensSourcePlanePhase):
        def pass_priors(self, results):

            ## Lens Light & Mass, Sersic -> Sersic, SIE -> SIE, Shear -> Shear ###

            self.lens_galaxies.lens = results.from_phase(
                "phase_4_lens_sersic_sie_shear_source_inversion"
            ).variable.lens_galaxies.lens

            # If the lens light is fixed, over-write the pass prior above to fix the lens light model.

            if pl_fix_lens_light:

                self.lens_galaxies.lens.light = results.from_phase(
                    "phase_4_lens_sersic_sie_shear_source_inversion"
                ).constant.lens_galaxies.lens.light

            ### Source Inversion, Inv -> Inv ###

            self.source_galaxies.source = results.from_phase(
                "phase_3_initialize_inversion"
            ).hyper_combined.constant.source_galaxies.source

            ## Set all hyper-galaxies if feature is turned on ##

            if pl_hyper_galaxies:

                self.lens_galaxies.lens.hyper_galaxy = (
                    results.last.hyper_combined.constant.lens_galaxies.lens.hyper_galaxy
                )

                self.source_galaxies.source.hyper_galaxy = (
                    results.last.hyper_combined.constant.source_galaxies.source.hyper_galaxy
                )

            if pl_hyper_background_sky:

                self.hyper_image_sky = (
                    results.last.hyper_combined.constant.hyper_image_sky
                )

            if pl_hyper_background_noise:

                self.hyper_noise_background = (
                    results.last.hyper_combined.constant.hyper_noise_background
                )

    phase4 = InversionPhase(
        phase_name="phase_4_lens_sersic_sie_shear_source_inversion",
        phase_folders=phase_folders,
        tag_phases=tag_phases,
        lens_galaxies=dict(
            lens=gm.GalaxyModel(
                redshift=redshift_lens,
                light=lp.EllipticalSersic,
                mass=mp.EllipticalIsothermal,
                shear=mp.ExternalShear,
            )
        ),
        source_galaxies=dict(
            source=gm.GalaxyModel(
                redshift=redshift_source,
                pixelization=pl_pixelization,
                regularization=pl_regularization,
            )
        ),
        sub_grid_size=sub_grid_size,
        bin_up_factor=bin_up_factor,
        positions_threshold=positions_threshold,
        inner_mask_radii=inner_mask_radii,
        interp_pixel_scale=interp_pixel_scale,
        inversion_pixel_limit=inversion_pixel_limit,
        cluster_pixel_scale=cluster_pixel_scale,
        optimizer_class=af.MultiNest,
    )

    phase4.optimizer.const_efficiency_mode = True
    phase4.optimizer.n_live_points = 75
    phase4.optimizer.sampling_efficiency = 0.2

    phase4 = phase4.extend_with_multiple_hyper_phases(
        hyper_galaxy=pl_hyper_galaxies,
        include_background_sky=pl_hyper_background_sky,
        include_background_noise=pl_hyper_background_noise,
        inversion=True,
    )

    return pipeline.PipelineImaging(pipeline_name, phase1, phase2, phase3, phase4)
