import autofit as af
import autolens as al

# In this pipeline, we'll perform a parametric source analysis which fits an image with a lens mass model and
# source galaxy.

# The pipeline is as follows:

# Phase 1:

# Fit the lens mass model and source light profile.

# Lens Mass: EllipticalIsothermal + ExternalShear
# Source Light: EllipticalSersic
# Previous Pipelines: None
# Prior Passing: None
# Notes: None


def make_pipeline(
    pipeline_general_settings,
    pipeline_source_settings,
    phase_folders=None,
    redshift_lens=0.5,
    redshift_source=1.0,
    positions_threshold=None,
    sub_size=2,
    signal_to_noise_limit=None,
    bin_up_factor=None,
    evidence_tolerance=100.0,
):

    ### SETUP PIPELINE & PHASE NAMES, TAGS AND PATHS ###

    pipeline_name = "pipeline_source__parametric__lens_sie__source_sersic"

    # This pipeline's name is tagged according to whether:

    # 1) Hyper-fitting settings (galaxies, sky, background noise) are used.
    # 2) The lens galaxy mass model includes an external shear.

    phase_folders.append(pipeline_name)
    phase_folders.append(
        pipeline_general_settings.tag + pipeline_source_settings.tag_no_inversion
    )

    ### PHASE 1 ###

    # In phase 1, we fit the lens galaxy's mass and source galaxy.

    phase1 = al.PhaseImaging(
        phase_name="phase_1__lens_sie__source_sersic",
        phase_folders=phase_folders,
        galaxies=dict(
            lens=al.GalaxyModel(
                redshift=redshift_lens,
                mass=al.mp.EllipticalIsothermal,
                shear=al.mp.ExternalShear,
            ),
            source=al.GalaxyModel(
                redshift=redshift_source, light=al.lp.EllipticalSersic
            ),
        ),
        positions_threshold=positions_threshold,
        sub_size=sub_size,
        signal_to_noise_limit=signal_to_noise_limit,
        bin_up_factor=bin_up_factor,
        optimizer_class=af.MultiNest,
    )

    phase1.optimizer.const_efficiency_mode = True
    phase1.optimizer.n_live_points = 80
    phase1.optimizer.sampling_efficiency = 0.2
    phase1.optimizer.evidence_tolerance = evidence_tolerance

    phase1 = phase1.extend_with_multiple_hyper_phases(
        hyper_galaxy=pipeline_general_settings.hyper_galaxies,
        include_background_sky=pipeline_general_settings.hyper_image_sky,
        include_background_noise=pipeline_general_settings.hyper_background_noise,
    )

    return al.PipelineDataset(pipeline_name, phase1)
