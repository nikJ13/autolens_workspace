import autofit as af
from autolens.model.galaxy import galaxy_model as gm
from autolens.pipeline.phase import phase_imaging, phase_extensions
from autolens.pipeline import pipeline
from autolens.pipeline import tagging as tag
from autolens.model.profiles import light_profiles as lp
from autolens.model.profiles import mass_profiles as mp

# In this pipeline, we'll perform a basic analysis which initialize a lens model (the lens's light, mass and source's \
# light) and then fits the source galaxy using an inversion. This pipeline uses three phases:

# Phase 1:

# Description: initialize and subtracts the lens light model.
# Lens Light: EllipticalSersic + EllipticalExponential
# Lens Mass: None
# Source Light: None
# Previous Pipelines: None
# Prior Passing: None
# Notes: None

# Phase 2:

# Description: initialize the lens mass model and source light profile, using the lens subtracted image from phase 1.
# Lens Light: None
# Lens Mass: EllipitcalIsothermal
# Source Light: EllipticalSersic
# Previous Pipelines: None
# Prior Passing: None
# Notes: Uses the lens light subtracted image from phase 1

# Phase 3:

# Description: Refine the lens light and mass models and source light profile, using priors from the previous 2 phases.
# Lens Light: EllipticalSersic + EllipticalExponential
# Lens Mass: EllipitcalIsothermal
# Source Light: EllipticalSersic
# Previous Pipelines: None
# Prior Passing: Lens light (variable -> phase 1), lens mass and source (variable -> phase 2)
# Notes: None


def make_pipeline(
    pl_align_bulge_disk_centre=False,
    pl_align_bulge_disk_axis_ratio=False,
    pl_align_bulge_disk_phi=False,
    pl_hyper_galaxies=True,
    pl_hyper_background_sky=True,
    pl_hyper_background_noise=True,
    phase_folders=None,
    tag_phases=True,
    redshift_lens=0.5,
    redshift_source=1.0,
    sub_grid_size=2,
    bin_up_factor=None,
    positions_threshold=None,
    inner_mask_radii=None,
    interp_pixel_scale=None,
):

    pipeline_name = tag.pipeline_name_from_name_and_settings(
        pipeline_name="pipeline_init__lens_sersic_exp_sie_source_sersic",
        align_bulge_disk_centre=pl_align_bulge_disk_centre,
        align_bulge_disk_axis_ratio=pl_align_bulge_disk_axis_ratio,
        align_bulge_disk_phi=pl_align_bulge_disk_phi,
    )

    phase_folders.append(pipeline_name)

    ### PHASE 1 ###

    # In phase 1, we will fit only the lens galaxy's light, where we:

    # 1) Set our priors on the lens galaxy (y,x) centre such that we assume the image is centred around the lens galaxy.
    # 2) Use a circular mask which includes the lens and source galaxy light.

    class BulgeDiskPhase(phase_imaging.LensPlanePhase):
        def pass_priors(self, results):

            if pl_align_bulge_disk_centre:
                self.lens_galaxies.lens.bulge.centre = (
                    self.lens_galaxies.lens.disk.centre
                )

            if pl_align_bulge_disk_axis_ratio:
                self.lens_galaxies.lens.bulge.axis_ratio = (
                    self.lens_galaxies.lens.disk.axis_ratio
                )

            if pl_align_bulge_disk_phi:
                self.lens_galaxies.lens.bulge.phi = self.lens_galaxies.lens.disk.phi

    phase1 = BulgeDiskPhase(
        phase_name="phase_1_lens_sersic_exp",
        phase_folders=phase_folders,
        tag_phases=tag_phases,
        lens_galaxies=dict(
            lens=gm.GalaxyModel(
                redshift=redshift_lens,
                bulge=lp.EllipticalSersic,
                disk=lp.EllipticalExponential,
            )
        ),
        sub_grid_size=sub_grid_size,
        bin_up_factor=bin_up_factor,
        optimizer_class=af.MultiNest,
    )

    # You'll see these lines throughout all of the example pipelines. They are used to make MultiNest sample the \
    # non-linear parameter space faster (if you haven't already, checkout the tutorial '' in howtolens/chapter_2).

    phase1.optimizer.const_efficiency_mode = True
    phase1.optimizer.n_live_points = 40
    phase1.optimizer.sampling_efficiency = 0.3

    phase1 = phase1.extend_with_multiple_hyper_phases(
        hyper_galaxy=pl_hyper_galaxies,
        include_background_sky=pl_hyper_background_sky,
        include_background_noise=pl_hyper_background_noise,
    )

    ### PHASE 2 ###

    # In phase 2, we will fit the lens galaxy's mass and source galaxy's light, where we:

    # 1) Use a lens-subtracted image generated by subtracting model lens galaxy image from phase 1.
    # 2) Initialize the priors on the centre of the lens galaxy's mass-profile by linking them to those inferred for \
    #    the bulge of the light profile in phase 1.
    # 3) Have the option to use an annular mask removing the central light, if the inner_mask_radii parametr is input.

    class LensSubtractedPhase(phase_imaging.LensSourcePlanePhase):
        def pass_priors(self, results):

            ## Lens Light Sersic -> Sersic, Exp -> Exp ##

            self.lens_galaxies.lens.bulge = results.from_phase(
                "phase_1_lens_sersic_exp"
            ).constant.lens_galaxies.lens.bulge
            self.lens_galaxies.lens.disk = results.from_phase(
                "phase_1_lens_sersic_exp"
            ).constant.lens_galaxies.lens.disk

            ## Lens Mass, Move centre priors to centre of lens light ###

            self.lens_galaxies.lens.mass.centre = (
                results.from_phase("phase_1_lens_sersic_exp")
                .variable_absolute(a=0.1)
                .lens_galaxies.lens.bulge.centre
            )

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

    phase2 = LensSubtractedPhase(
        phase_name="phase_2_lens_sie_source_sersic",
        phase_folders=phase_folders,
        tag_phases=tag_phases,
        lens_galaxies=dict(
            lens=gm.GalaxyModel(
                redshift=redshift_lens,
                bulge=lp.EllipticalSersic,
                disk=lp.EllipticalExponential,
                mass=mp.EllipticalIsothermal,
            )
        ),
        source_galaxies=dict(
            source=gm.GalaxyModel(redshift=redshift_source, light=lp.EllipticalSersic)
        ),
        sub_grid_size=sub_grid_size,
        bin_up_factor=bin_up_factor,
        positions_threshold=positions_threshold,
        inner_mask_radii=inner_mask_radii,
        interp_pixel_scale=interp_pixel_scale,
        optimizer_class=af.MultiNest,
    )

    phase2.optimizer.const_efficiency_mode = False
    phase2.optimizer.n_live_points = 50
    phase2.optimizer.sampling_efficiency = 0.3

    phase2 = phase2.extend_with_multiple_hyper_phases(
        hyper_galaxy=pl_hyper_galaxies,
        include_background_sky=pl_hyper_background_sky,
        include_background_noise=pl_hyper_background_noise,
    )

    ### PHASE 3 ###

    # In phase 3, we will fit simultaneously the lens and source galaxies, where we:

    # 1) Initialize the lens's light, mass, shear and source's light using the results of phases 1 and 2.
    # 2) Use a circular mask, to fully capture the lens and source light.

    class LensSourcePhase(phase_imaging.LensSourcePlanePhase):
        def pass_priors(self, results):

            ## Lens Light, Sersic -> Sersic ###

            self.lens_galaxies.lens.bulge = results.from_phase(
                "phase_1_lens_sersic_exp"
            ).variable.lens_galaxies.lens.bulge

            self.lens_galaxies.lens.disk = results.from_phase(
                "phase_1_lens_sersic_exp"
            ).variable.lens_galaxies.lens.disk

            ## Lens Mass, SIE -> SIE, Shear -> Shear ###

            self.lens_galaxies.lens.mass = results.from_phase(
                "phase_2_lens_sie_source_sersic"
            ).variable.lens_galaxies.lens.mass

            ### Source Light, Sersic -> Sersic, Exp -> Exp ###

            self.source_galaxies.source = results.from_phase(
                "phase_2_lens_sie_source_sersic"
            ).variable.source_galaxies.source

            ## Set all hyper-galaxies if feature is turned on ##

            if pl_hyper_galaxies:

                self.lens_galaxies.lens.hyper_galaxy = results.from_phase(
                    "phase_1_lens_sersic_exp"
                ).hyper_combined.constant.lens_galaxies.lens.hyper_galaxy

            if pl_hyper_background_sky:

                self.hyper_image_sky = (
                    results.last.hyper_combined.constant.hyper_image_sky
                )

            if pl_hyper_background_noise:

                self.hyper_noise_background = (
                    results.last.hyper_combined.constant.hyper_noise_background
                )

    phase3 = LensSourcePhase(
        phase_name="phase_3_lens_sersic_exp_sie_source_sersic",
        phase_folders=phase_folders,
        tag_phases=tag_phases,
        lens_galaxies=dict(
            lens=gm.GalaxyModel(
                redshift=redshift_lens,
                bulge=lp.EllipticalSersic,
                disk=lp.EllipticalExponential,
                mass=mp.EllipticalIsothermal,
            )
        ),
        source_galaxies=dict(
            source=gm.GalaxyModel(redshift=redshift_source, light=lp.EllipticalSersic)
        ),
        sub_grid_size=sub_grid_size,
        bin_up_factor=bin_up_factor,
        positions_threshold=positions_threshold,
        interp_pixel_scale=interp_pixel_scale,
        optimizer_class=af.MultiNest,
    )

    phase3.optimizer.const_efficiency_mode = True
    phase3.optimizer.n_live_points = 75
    phase3.optimizer.sampling_efficiency = 0.3

    phase3 = phase3.extend_with_multiple_hyper_phases(
        hyper_galaxy=pl_hyper_galaxies,
        include_background_sky=pl_hyper_background_sky,
        include_background_noise=pl_hyper_background_noise,
    )

    return pipeline.PipelineImaging(pipeline_name, phase1, phase2, phase3)
