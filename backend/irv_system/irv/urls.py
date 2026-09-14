from django.urls import path

from . import views

urlpatterns = [
    path("rules/", views.RuleSnapshotView.as_view(), name="rules"),
    path("elections/", views.ElectionListCreateView.as_view(), name="election-list"),
    path("elections/<slug:slug>/", views.ElectionDetailView.as_view(),
         name="election-detail"),
    path("elections/<slug:slug>/compute/", views.ElectionComputeView.as_view(),
         name="election-compute"),
    path("elections/<slug:slug>/publish/", views.ElectionPublishView.as_view(),
         name="election-publish"),
    path("elections/<slug:slug>/ballots/<str:code>/",
         views.BallotChainView.as_view(), name="ballot-chain"),
]
