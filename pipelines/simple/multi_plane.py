import autofit as af
import autolens as al

############## THIS PIPELINE IS A WORK IN PROGRESS AND I DO NOT RECOMMEND YOU TRY TO USE IT TO DO LENS MODELING ########

# In this pipeline, we'll perform an advanced analysis which fits a lens galaxy with three surrounding line-of-sight \
# galaxies (which are at different redshifts and thus define a multi-plane stronog lens configuration). The source \
# galaxy will be modeled using a parametric light profile in the initial phases, but switch to an inversion in the \
# later phases.

# For efficiency, we will subtract the lens galaxy's light and line-of-sight galaxies light, and then only fit a
# foreground subtracted image. This means we can use an annular mask tailored to the source galaxy's light, which we
# have setup already using the 'tools/mask_maker.py' scripts.

# This leads to a 5 phase pipeline:

# Phase 1) Fit and subtract the light profile of the lens galaxy (elliptical Sersic) and each line-of-sight
#          galaxy (spherical Sersic).

# Phase 2) Use this lens subtracted image to fit the lens galaxy's mass (SIE) and source galaxy's light (Sersic),
#          thereby omitting multi-plane ray-tracing.

# Phase 3) Initialize the resolution and regularization coefficient of the inversion using the best-fit lens model from
#          phase 2.

# Phase 4) Refit the lens galaxy's light and mass models using an inversion (with priors from the above phases). The
#          mass profile of the 3 line-of-sight galaxies is also included (as SIS profiles), but a single lens plane
#          is assumed.

# Phase 5) Fit the lens galaxy, line-of-sight galaxies and source-galaxy using multi-plane ray-tracing, where the
#          redshift of each line-of-sight galaxy is included in the non-linear search as a free parameter. This phase
#          uses priors initialized from phase 4.

# Phase 5 risks the inversion falling into the systematic solutions where the mass of the lens model is too high,
# resulting in the inversion reconstructing the image as a demagnified version of itself. This is because the \
# line-of-sight halos each have a mass, which during the modeling can go to very high values.

# For this reason, we include positions (drawn using the 'tools/position_thresholding.py' script) to prevent these solutions from
# existing in parameter space.


def make_pipeline(phase_folders=None):

    ### SETUP PIPELINE AND PHASE NAMES, TAGS AND PATHS ###

    # We setup the pipeline name using the tagging module. In this case, the pipeline name is not given a tag and
    # will be the string specified below However, its good practise to use the 'tag.' function below, incase
    # a pipeline does use customized tag names.

    pipeline_name = "pipeline_multi_plane"
    pipeline_tag = al.pipeline_tagging.pipeline_tag_from_pipeline_settings()

    # This function uses the phase folders and pipeline name to set up the output directory structure,
    # e.g. 'autolens_workspace/output/phase_folder_1/phase_folder_2/pipeline_name/phase_name/'

    phase_folders.append(pipeline_name)
    phase_folders.append(pipeline_tag)

    # In phase 1, we will:

    # 1) Subtract the light of the main lens galaxy (located at (0.0", 0.0")) and the light of each line-of-sight
    # galaxy (located at (4.0", 4.0"), (3.6", -5.3") and (-3.1", -2.4"))

    lens = al.GalaxyModel(light=al.lp.EllipticalSersic)
    lens.light.centre_0 = af.GaussianPrior(mean=0.0, sigma=0.1)
    lens.light.centre_1 = af.GaussianPrior(mean=0.0, sigma=0.1)

    los_0 = al.GalaxyModel(light=al.lp.SphericalSersic)
    los_0.light.centre_0 = af.GaussianPrior(mean=4.0, sigma=0.1)
    los_0.light.centre_1 = af.GaussianPrior(mean=4.0, sigma=0.1)

    los_1 = al.GalaxyModel(light=al.lp.SphericalSersic)
    los_1.light.centre_0 = af.GaussianPrior(mean=3.6, sigma=0.1)
    los_1.light.centre_1 = af.GaussianPrior(mean=-5.3, sigma=0.1)

    los_2 = al.GalaxyModel(light=al.lp.SphericalSersic)
    los_2.light.centre_0 = af.GaussianPrior(mean=-3.1, sigma=0.1)
    los_2.light.centre_1 = af.GaussianPrior(mean=-2.4, sigma=0.1)

    phase1 = al.PhaseImaging(
        phase_name="phase_1__light_subtraction",
        phase_folders=phase_folders,
        galaxies=dict(lens=lens, los_0=los_0, los_1=los_1, los_2=los_2),
        optimizer_class=af.MultiNest,
    )

    # Customize MultiNest so it runs fast
    phase1.optimizer.n_live_points = 80
    phase1.optimizer.sampling_efficiency = 0.2
    phase1.optimizer.const_efficiency_mode = True

    # In phase 2, we will:

    # 1) Fit this foreground subtracted image, using an SIE+Shear mass model and Sersic source.
    # 2) Use the input positions to resample inaccurate mass models.

    class LensSubtractedPhase(al.PhaseImaging):
        def modify_image(self, image, results):
            return (
                image
                - results.from_phase(
                    "phase_1__light_subtraction"
                ).unmasked_lens_power_lawane_model_image
            )

    mass = af.PriorModel(mass=al.mp.EllipticalIsothermal)
    mass.centre_0 = af.GaussianPrior(mean=0.0, sigma=0.1)
    mass.centre_1 = af.GaussianPrior(mean=0.0, sigma=0.1)

    phase2 = LensSubtractedPhase(
        phase_name="phase_2__source_parametric",
        phase_folders=phase_folders,
        galaxies=dict(
            lens=al.GalaxyModel(mass=mass),
            source=al.GalaxyModel(light=al.lp.EllipticalSersic),
        ),
        positions_threshold=0.3,
        optimizer_class=af.MultiNest,
    )

    phase2.optimizer.n_live_points = 50
    phase2.optimizer.sampling_efficiency = 0.2
    phase2.optimizer.const_efficiency_mode = True

    # In phase 3, we will:

    #  1) Fit the foreground subtracted image using a source-inversion instead of parametric source, using lens galaxy
    #     priors from phase 2.

    class InversionPhase(al.PhaseImaging):
        def modify_image(self, image, results):
            return (
                image
                - results.from_phase(
                    "phase_1__light_subtraction"
                ).unmasked_lens_power_lawane_model_image
            )

    phase3 = InversionPhase(
        phase_name="phase_3__inversion_init",
        phase_folders=phase_folders,
        galaxies=dict(
            lens=al.GalaxyModel(mass=phase2.result.instance.galaxies.lens.mass),
            source=al.GalaxyModel(
                pixelization=al.pix.VoronoiMagnification, regularization=al.reg.Constant
            ),
        ),
        optimizer_class=af.MultiNest,
    )

    # Customize MultiNest so it runs fast
    phase3.optimizer.n_live_points = 10
    phase3.optimizer.sampling_efficiency = 0.5
    phase3.optimizer.const_efficiency_mode = True

    # In phase 4, we will:

    #  1) Fit the foreground subtracted image using a source-inversion with parameters initialized from phase 3.
    #  2) Initialize the lens galaxy priors using the results of phase 2, and include each line-of-sight galaxy's mass
    #     contribution (keeping its centre fixed to the light profile centred inferred in phase 1). This will assume
    #     a single lens plane for all line-of-sight galaxies.
    #  3) Use the input positions to resample inaccurate mass models.

    class SingleLensPlanePhase(al.PhaseImaging):
        def modify_image(self, image, results):
            return (
                image
                - results.from_phase(
                    "phase_1__light_subtraction"
                ).unmasked_lens_power_lawane_model_image
            )

    los_0 = al.GalaxyModel(mass=al.mp.SphericalIsothermal)
    los_0.mass.centre_0 = phase3.result.instance.los_0.light.centre_0
    los_0.mass.centre_1 = phase3.result.instance.los_0.light.centre_1

    los_1 = al.GalaxyModel(mass=al.mp.SphericalIsothermal)
    los_1.mass.centre_0 = phase3.result.instance.los_1.light.centre_0
    los_1.mass.centre_1 = phase3.result.instance.los_1.light.centre_1

    los_2 = al.GalaxyModel(mass=al.mp.SphericalIsothermal)
    los_2.mass.centre_0 = phase3.result.instance.los_2.light.centre_0
    los_2.mass.centre_1 = phase3.result.instance.los_2.light.centre_1

    phase4 = SingleLensPlanePhase(
        phase_name="phase_4__single_plane",
        phase_folders=phase_folders,
        galaxies=dict(
            lens=al.GalaxyModel(mass=phase3.result.model.lens.mass),
            los_0=los_0,
            los_1=los_1,
            los_2=los_2,
            source=al.GalaxyModel(
                pixelization=phase3.result.instance.galaxies.source.pixelization,
                regularization=phase3.result.instance.galaxies.source.regularization,
            ),
        ),
        positions_threshold=0.3,
        optimizer_class=af.MultiNest,
    )

    # Customize MultiNest so it runs fast
    phase4.optimizer.n_live_points = 60
    phase4.optimizer.sampling_efficiency = 0.2
    phase4.optimizer.const_efficiency_mode = True

    # In phase 5, we will fit the foreground subtracted image using a multi-plane ray tracer. This means that the
    # redshift of each line-of-sight galaxy is included as a free parameter (we assume the lens and source redshifts
    # are known).

    class MultiPlanePhase(al.PhaseImaging):
        def modify_image(self, image, results):
            return (
                image
                - results.from_phase(
                    "phase_1__light_subtraction"
                ).unmasked_lens_power_lawane_model_image
            )

    phase5 = MultiPlanePhase(
        phase_name="phase_5_multi_plane",
        phase_folders=phase_folders,
        galaxies=dict(
            lens=al.GalaxyModel(mass == phase4.result.model.galaxies.lens.mass),
            los_0=al.GalaxyModel(
                mass=phase4.result.model.galaxies.los_0.mass, variable_redshift=True
            ),
            los_1=al.GalaxyModel(
                mass=phase4.result.model.galaxies.los_1.mass, variable_redshift=True
            ),
            los_2=al.GalaxyModel(
                mass=phase4.result.model.galaxies.los_2.mass, variable_redshift=True
            ),
            source=al.GalaxyModel(
                pixelization=phase4.result.model.galaxies.source.pixelization,
                regularization=phase4.result.model.galaxies.source.regularization,
            ),
        ),
        positions_threshold=0.3,
        optimizer_class=af.MultiNest,
    )

    # Customize MultiNest so it runs fast
    phase5.optimizer.n_live_points = 60
    phase5.optimizer.sampling_efficiency = 0.2
    phase5.optimizer.const_efficiency_mode = True

    return al.PipelineDataset(pipeline_name, phase1, phase2, phase3, phase4, phase5)
