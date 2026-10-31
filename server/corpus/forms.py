"""后台表单：控制各字段的控件尺寸，避免 JSON 字段一律撑成巨框。"""
from django import forms

from .models import Work

TEXTAREA_SMALL = forms.Textarea(attrs={"rows": 3, "class": "vLargeTextField"})
TEXTAREA_MED = forms.Textarea(attrs={"rows": 6, "class": "vLargeTextField"})
TEXTAREA_BIG = forms.Textarea(attrs={"rows": 14, "class": "vLargeTextField", "style": "font-family: ui-monospace, monospace;"})


class WorkAdminForm(forms.ModelForm):
    class Meta:
        model = Work
        fields = "__all__"
        widgets = {
            "aliases": TEXTAREA_SMALL,
            "notes": TEXTAREA_MED,
            "paragraphs": TEXTAREA_BIG,
            "paragraphs_simplified": TEXTAREA_BIG,
            "meaning": TEXTAREA_MED,
            "background": TEXTAREA_MED,
            "appreciation": TEXTAREA_MED,
            "inference": TEXTAREA_SMALL,
            "inference_basis": TEXTAREA_SMALL,
        }
